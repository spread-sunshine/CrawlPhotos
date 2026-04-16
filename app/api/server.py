# -*- coding: utf-8 -*-
"""
API Service Layer (FastAPI).
API服务层 - REST接口，支持Web管理界面.

Provides HTTP endpoints for:
    - Manual trigger of crawl/recognize/upload pipelines
    - Photo listing, search, detail queries, and file serving
    - Calendar view data by month/year
    - System status dashboard and statistics
    - Review pool management (approve/reject)
    - Metrics export (Prometheus format)
    - Configuration inspection (read-only)

This server is **disabled by default**. Enable via:
    config.yaml -> api.enabled = true

Security note:
    - Intended for LOCAL use only (127.0.0.1)
    - No authentication in MVP phase
    - Will be hardened before public exposure
"""

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger
from app.database.db import Database

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app):  # type: ignore
    """FastAPI lifespan: startup/shutdown hooks."""
    logger.info("API Server starting up")
    yield
    logger.info("API Server shutting down")


def create_app(
    db: Optional[Database] = None,
    orchestrator=None,
) -> Any:
    """
    Create and configure FastAPI application instance.

    Args:
        db: Database instance for data access.
        orchestrator: Orchestrator instance for triggering runs.
    
    Returns:
        Configured FastAPI app (or None if fastapi not installed).
    """
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import (
            FileResponse,
            JSONResponse,
            Response,
        )
        from pydantic import BaseModel
    except ImportError:
        logger.warning(
            "FastAPI not installed. Install with: "
            "pip install fastapi uvicorn"
        )
        return None

    app = FastAPI(
        title="CrawlPhotos API",
        description="Baby Photos Auto Crawler REST API",
        version="2.0.0",
        lifespan=_lifespan,
    )

    _db = db
    _orch = orchestrator

    # ==================== Models ====================

    class HealthResponse(BaseModel):
        status: str
        timestamp: str
        database_connected: bool
        components: Dict[str, str]

    class TaskTriggerRequest(BaseModel):
        trigger_type: str = "manual"
        options: Dict[str, Any] = {}

    class TaskTriggerResponse(BaseModel):
        success: bool
        message: str
        task_id: Optional[str] = None

    class PhotoListItem(BaseModel):
        photo_id: str
        source_photo_id: str = ""
        upload_time: Optional[str] = None
        local_path: Optional[str] = None
        contains_target: bool = False
        confidence: float = 0.0
        status: str = ""
        created_at: str = ""

    class ApiResponse(BaseModel):
        code: int
        message: str
        data: Any = None

    class ReviewApproveRequest(BaseModel):
        reviewer: str = "admin"
        note: str = ""

    # ==================== Endpoints ====================

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """System health endpoint."""
        db_ok = False
        if _db:
            try:
                _db.execute_query("SELECT 1")
                db_ok = True
            except Exception:
                pass

        return HealthResponse(
            status="healthy" if db_ok else "degraded",
            timestamp=datetime.now().isoformat(),
            database_connected=db_ok,
            components={
                "database": (
                    "connected"
                    if db_ok else "disconnected"
                ),
                "orchestrator": (
                    "loaded" if _orch else "none"
                ),
            },
        )

    # ---- Task Management ----

    @app.post(
        "/api/v1/tasks/trigger",
        response_model=TaskTriggerResponse,
    )
    async def trigger_task(req: TaskTriggerRequest):
        """Manually trigger a crawl + recognize pipeline run."""
        if not _orch:
            raise HTTPException(
                status_code=503,
                detail="Orchestrator not configured",
            )

        task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_run_orchestrator_async(req.options))
            return TaskTriggerResponse(
                success=True,
                message="Task triggered successfully",
                task_id=task_id,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to trigger task: {e}",
            )

    @app.get("/api/v1/tasks/recent")
    async def list_recent_tasks(limit: int = Query(10, ge=1, le=50)):
        """List recent pipeline runs (tasks)."""
        if not _db:
            raise HTTPException(status_code=503)

        try:
            rows = _db.execute_query_all(
                "SELECT * FROM pipeline_runs "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            return ApiResponse(
                code=0,
                message="success",
                data={"items": [dict(r) for r in (rows or [])]},
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            )

    # ---- Photo CRUD ----

    @app.get("/api/v1/photos", response_model=ApiResponse)
    async def list_photos(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        target_only: bool = Query(False),
        status_filter: Optional[str] = Query(None),
    ):
        """List photos with pagination and filtering."""
        if not _db:
            raise HTTPException(
                status_code=503,
                detail="Database not available",
            )

        offset = (page - 1) * page_size
        where_parts = []
        params: list = []

        if target_only:
            where_parts.append("contains_target = 1")
        if status_filter:
            where_parts.append("status = ?")
            params.append(status_filter)

        where_clause = (
            (" AND ".join(where_parts)) if where_parts else "1=1"
        )

        count_row = _db.execute_query_one(
            f"SELECT COUNT(*) AS total "
            f"FROM photos_record WHERE {where_clause}",
            params,
        )
        total = count_row["total"] if count_row else 0

        rows = _db.execute_query_all(
            f"SELECT * FROM photos_record WHERE {where_clause} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )

        items = []
        for r in rows or []:
            items.append(PhotoListItem(
                photo_id=r.get("photo_id", ""),
                source_photo_id=r.get(
                    "source_photo_id", ""
                ),
                upload_time=r.get("upload_time"),
                local_path=r.get("local_path"),
                contains_target=bool(r.get("contains_target")),
                confidence=float(r.get("confidence") or 0),
                status=r.get("status", "unknown"),
                created_at=r.get("created_at", ""),
            ))

        return ApiResponse(
            code=0,
            message="success",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        )

    @app.get("/api/v1/photos/{photo_id}", response_model=ApiResponse)
    async def get_photo_detail(photo_id: str):
        """Get detailed info about a single photo."""
        if not _db:
            raise HTTPException(status_code=503)

        row = _db.execute_query_one(
            "SELECT * FROM photos_record WHERE photo_id=?",
            (photo_id,),
        )
        if not row:
            raise HTTPException(
                status_code=404, detail="Photo not found",
            )

        return ApiResponse(code=0, message="success", data=dict(row))

    @app.get("/api/v1/photos/{photo_id}/file")
    async def serve_photo_file(photo_id: str, size: str = "original"):
        """Serve a photo file (original or thumbnail).

        Args:
            size: 'original' for full image, 'thumb' for thumbnail.
        """
        if not _db:
            raise HTTPException(status_code=503)

        row = _db.execute_query_one(
            "SELECT local_path, stored_path FROM photos_record WHERE photo_id=?",
            (photo_id,),
        )
        if not row:
            raise HTTPException(
                status_code=404, detail="Photo not found",
            )

        path_str = row["stored_path"] or row["local_path"]
        if not path_str:
            raise HTTPException(
                status_code=404,
                detail="Photo file not available on disk",
            )

        file_path = Path(path_str)
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {path_str}",
            )

        if size == "thumb":
            # Return a small thumbnail using PIL
            from PIL import Image
            import io

            img = Image.open(file_path)
            img.thumbnail((400, 400), Image.LANCZOS)

            buf = io.BytesIO()
            ext = file_path.suffix.lower()
            fmt = "JPEG" if ext in (".jpg", ".jpeg") else "PNG"
            img.save(buf, format=fmt, quality=75)

            buf.seek(0)
            media = (
                "image/jpeg" if fmt == "JPEG" else "image/png"
            )
            return Response(content=buf.read(), media_type=media)

        return FileResponse(str(file_path), media_type=_guess_media_type(file_path))

    # ---- Calendar View ----

    @app.get("/api/v1/photos/calendar/{year}/{month}")
    async def calendar_data(year: int, month: int):
        """Get photo counts grouped by day for a given month."""
        if not _db:
            raise HTTPException(status_code=503)

        start = f"{year}-{month:02d}-01"

        if month == 12:
            end = f"{year + 1}-01-01"
        else:
            end = f"{year}-{month + 1:02d}-01"

        try:
            rows = _db.execute_query_all(
                "SELECT DATE(created_at) AS day, "
                "COUNT(*) AS count, "
                "SUM(CASE WHEN contains_target=1 THEN 1 ELSE 0 END) "
                "AS target_count "
                "FROM photos_record "
                "WHERE created_at >= ? AND created_at < ? "
                "GROUP BY DATE(created_at) ORDER BY day",
                (start, end),
            )

            daily_data = {}
            for r in rows or []:
                daily_data[r["day"]] = {
                    "total": r["count"],
                    "target": r["target_count"] or 0,
                }

            return ApiResponse(
                code=0,
                message="success",
                data={
                    "year": year,
                    "month": month,
                    "daily": daily_data,
                },
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            )

    # ---- Statistics & Status ----

    @app.get("/api/v1/stats", response_model=ApiResponse)
    async def get_statistics():
        """Return system statistics."""
        stats: Dict[str, Any] = {}

        if _db:
            try:
                r = _db.execute_query_one(
                    "SELECT COUNT(*) AS total FROM photos_record",
                )
                stats["total_photos"] = r["total"] if r else 0

                r2 = _db.execute_query_one(
                    "SELECT COUNT(*) AS cnt FROM photos_record WHERE contains_target=1",
                )
                stats["target_matches"] = r2["cnt"] if r2 else 0

                rows = _db.execute_query_all(
                    "SELECT status, COUNT(*) AS cnt FROM photos_record GROUP BY status",
                )
                stats["by_status"] = {
                    r["status"]: r["cnt"]
                    for r in (rows or [])
                }

                r3 = _db.execute_query_one(
                    "SELECT MAX(created_at) AS latest FROM photos_record",
                )
                stats["latest_activity"] = (
                    r3["latest"] if r3 else "never"
                )

                # Disk usage for storage directory
                storage_root = "./output"
                if os.path.exists(storage_root):
                    total, used, free = shutil.disk_usage(
                        storage_root
                    )
                    stats["disk_usage_bytes"] = used
                    stats["disk_free_bytes"] = free

                # Pipeline run stats
                r4 = _db.execute_query_one(
                    "SELECT COUNT(*) AS cnt FROM pipeline_runs",
                )
                stats["total_runs"] = r4["cnt"] if r4 else 0

            except Exception as e:
                stats["error"] = str(e)

        return ApiResponse(code=0, message="success", data=stats)

    @app.get("/api/v1/status", response_model=ApiResponse)
    async def system_status():
        """Comprehensive system status dashboard."""
        status_data: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "modules": {},
        }

        if _db:
            status_data["modules"]["database"] = "connected"
        else:
            status_data["modules"]["database"] = "not configured"

        if _orch:
            status_data["modules"]["orchestrator"] = "loaded"
        else:
            status_data["modules"]["orchestrator"] = "not loaded"

        return ApiResponse(code=0, message="success", data=status_data)

    # ---- Metrics / Prometheus ----

    @app.get("/metrics")
    async def prometheus_metrics():
        """Export metrics in Prometheus text format."""
        try:
            from app.core.metrics import get_metrics
            collector = get_metrics()
            text = collector.export_prometheus()
            return Response(content=text, media_type="text/plain; version=0.0.4; charset=utf-8")
        except Exception as e:
            return Response(
                content=f"# Error loading metrics: {e}\n",
                media_type="text/plain",
            )

    @app.get("/api/v1/metrics/snapshot", response_model=ApiResponse)
    async def metrics_snapshot():
        """Return metrics snapshot as JSON."""
        try:
            from app.core.metrics import get_metrics
            collector = get_metrics()
            snap = collector.get_snapshot()
            return ApiResponse(code=0, message="success", data=snap)
        except Exception as e:
            return ApiResponse(
                code=-1, message=str(e), data=None,
            )

    # ---- Review Pool ----

    @app.get("/api/v1/review", response_model=ApiResponse)
    async def list_review_items(
        status: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=100),
    ):
        """List review pool items."""
        try:
            from app.core.review_pool import ReviewPool, ReviewStatus
            pool = ReviewPool()

            if status:
                items = pool.list_items(
                    status=status, limit=limit
                )
            else:
                items = pool.list_items(limit=limit)

            summary = pool.get_summary()

            return ApiResponse(
                code=0,
                message="success",
                data={
                    "items": [i.to_dict() for i in items],
                    "summary": summary,
                },
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            )

    @app.post("/api/v1/review/{item_id}/approve", response_model=ApiResponse)
    async def approve_review_item(item_id: int, req: ReviewApproveRequest):
        """Approve a review item (confirm it's a target photo)."""
        try:
            from app.core.review_pool import ReviewPool
            pool = ReviewPool()
            ok = pool.approve(item_id, req.reviewer, req.note)
            if ok:
                return ApiResponse(
                    code=0,
                    message="Approved successfully",
                    data={"id": item_id},
                )
            raise HTTPException(
                status_code=404,
                detail="Item not found or already reviewed",
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/review/{item_id}/reject", response_model=ApiResponse)
    async def reject_review_item(item_id: int, req: ReviewApproveRequest):
        """Reject a review item (confirm it's NOT a target)."""
        try:
            from app.core.review_pool import ReviewPool
            pool = ReviewPool()
            ok = pool.reject(item_id, req.reviewer, req.note)
            if ok:
                return ApiResponse(
                    code=0,
                    message="Rejected successfully",
                    data={"id": item_id},
                )
            raise HTTPException(
                status_code=404,
                detail="Item not found or already reviewed",
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/review/summary", response_model=ApiResponse)
    async def review_summary():
        """Get review pool summary counts."""
        try:
            from app.core.review_pool import ReviewPool
            pool = ReviewPool()
            summary = pool.get_summary()
            return ApiResponse(
                code=0, message="success", data=summary,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


async def _run_orchestrator_async(options: Dict[str, Any]) -> None:
    """Background runner for orchestrator tasks."""
    logger.info(
        "Background task started with options: %s", options
    )


def _guess_media_type(path: Path) -> str:
    """Guess MIME type from file extension."""
    suffix_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return suffix_map.get(path.suffix.lower(), "application/octet-stream")


def start_api_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    db: Optional[Database] = None,
    orchestrator=None,
) -> None:
    """
    Start the FastAPI server (blocking).

    Should be called in a separate thread or process.
    """
    app = create_app(db=db, orchestrator=orchestrator)
    if app is None:
        logger.error("Cannot start API server: FastAPI not installed")
        return

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
