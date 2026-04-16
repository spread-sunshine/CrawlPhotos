# -*- coding: utf-8 -*-
"""
API Service Layer (FastAPI).
API服务层 - 为V2.0铺路的REST接口，默认关闭.

Provides HTTP endpoints for:
    - Manual trigger of crawl/recognize/upload pipelines
    - Photo listing, search, and detail queries
    - System status dashboard
    - Configuration inspection (read-only)

This server is **disabled by default**. Enable via:
    config.yaml -> api.enabled = true

Security note:
    - Intended for LOCAL use only (127.0.0.1)
    - No authentication in MVP phase
    - Will be hardened before public exposure
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config.logging_config import get_logger
from app.database.db import Database

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app):  # type: ignore
    """FastAPI lifespan: startup/shutdown hooks."""
    # Startup
    logger.info("API Server starting up")
    yield
    # Shutdown
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
        from fastapi.responses import JSONResponse
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
        version="1.0.0",
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
        source_photo_id: str
        upload_time: Optional[str]
        local_path: Optional[str]
        contains_target: bool
        confidence: float
        status: str
        created_at: str

    class ApiResponse(BaseModel):
        code: int
        message: str
        data: Any = None

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
                "database": "connected" if db_ok else "disconnected",
                "orchestrator": (
                    "loaded" if _orch else "none"
                ),
            },
        )

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
            # Fire-and-forget: start task in background
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
                status_code=503, detail="Database not available",
            )

        offset = (page - 1) * page_size
        where_parts = []
        params: list = []

        if target_only:
            where_parts.append("contains_target = 1")
        if status_filter:
            where_parts.append("status = ?")
            params.append(status_filter)

        where_clause = (" AND ".join(where_parts)) if where_parts else "1=1"

        count_row = _db.execute_query_one(
            f"SELECT COUNT(*) AS total FROM photos_record WHERE {where_clause}",
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
                source_photo_id=r.get("source_photo_id", ""),
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

    @app.get("/api/v1/stats", response_model=ApiResponse)
    async def get_statistics():
        """Return system statistics."""
        stats: Dict[str, Any] = {}

        if _db:
            try:
                # Total photos
                r = _db.execute_query_one(
                    "SELECT COUNT(*) AS total FROM photos_record",
                )
                stats["total_photos"] = r["total"] if r else 0

                # Target matches
                r2 = _db.execute_query_one(
                    "SELECT COUNT(*) AS cnt FROM photos_record WHERE contains_target=1",
                )
                stats["target_matches"] = r2["cnt"] if r2 else 0

                # Status breakdown
                rows = _db.execute_query_all(
                    "SELECT status, COUNT(*) AS cnt FROM photos_record GROUP BY status",
                )
                stats["by_status"] = {
                    r["status"]: r["cnt"]
                    for r in (rows or [])
                }

                # Recent activity
                r3 = _db.execute_query_one(
                    "SELECT MAX(created_at) AS latest FROM photos_record",
                )
                stats["latest_activity"] = (
                    r3["latest"] if r3 else "never"
                )
            except Exception as e:
                stats["error"] = str(e)

        return ApiResponse(code=0, message="success", data=stats)

    @app.get("/api/v1/status", response_model=ApiResponse)
    async def system_status():
        """Comprehensive system status dashboard."""
        status_data: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
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

    return app


async def _run_orchestrator_async(options: Dict[str, Any]) -> None:
    """Background runner for orchestrator tasks."""
    # This is a placeholder; actual implementation would call
    # the orchestrator's run method asynchronously
    logger.info("Background task started with options: %s", options)


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
        logger.error("Cannot start API server: FastAPI not available")
        return

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
