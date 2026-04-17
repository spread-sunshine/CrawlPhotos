# -*- coding: utf-8 -*-
"""Start API server with full Orchestrator support."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))
sys.dont_write_bytecode = True

from app.config.settings import Settings
from app.database.db import Database
from app.face_recognition.facade import FaceRecognizerFacade
from app.face_recognition.models import TargetConfig
from app.crawler.local_file_crawler import (
    LocalFileCrawler, LocalFileConfig,
)
from app.preprocessor.image_pipeline import ImagePreprocessor, PreprocessConfig
from app.storage.local_storage import StorageManager
from app.orchestrator import Orchestrator
from app.api.server import create_app


async def main():
    settings = Settings.load()
    db = Database()
    db.initialize()

    face_cfg = settings.get_section("face_recognition")
    recognizer = FaceRecognizerFacade(face_cfg)

    targets_cfg = settings.get("face_recognition.targets", [])
    targets = []
    for tc in targets_cfg:
        ref_dir = tc.get("reference_photos_dir", "")
        ref_paths = []
        if ref_dir:
            ref_dir_path = Path(ref_dir)
            if ref_dir_path.exists():
                exts = {".jpg", ".jpeg", ".png", ".webp"}
                ref_paths = [
                    p
                    for p in sorted(ref_dir_path.iterdir())
                    if p.suffix.lower() in exts
                ]
        targets.append(
            TargetConfig(
                name=tc.get("name", "Unknown"),
                reference_photo_paths=ref_paths,
                min_confidence=tc.get("min_confidence", 0.80),
                enabled=tc.get("enabled", True),
            )
        )
    if targets:
        await recognizer.initialize(targets)

    source_type = settings.get("source.type", "qq_group_album")
    if source_type == "local_directory":
        local_cfg = settings.get_section("source.local_directory")
        crawler = LocalFileCrawler(
            config=LocalFileConfig(
                source_dir=local_cfg.get("path", "test_photos/"),
                recursive=local_cfg.get("recursive", True),
            )
        )
    else:
        from app.crawler.qq_album_crawler import QQAlbumCrawler

        crawler = QQAlbumCrawler(
            group_id=settings.require("qq.group.group_id"),
            cookies_file=settings.get(
                "qq.group.cookies_file",
                "data/qq_cookies.txt",
            ),
        )

    preprocessor = ImagePreprocessor(
        PreprocessConfig(max_width=2048, max_height=2048, jpeg_quality=85)
    )
    storage_root = settings.get("storage.root_directory", "./output")
    storage = StorageManager(root_directory=storage_root)

    orch = Orchestrator(
        settings=settings,
        database=db,
        recognizer=recognizer,
        crawler=crawler,
        preprocessor=preprocessor,
        storage_manager=storage,
    )

    app = create_app(db=db, orchestrator=orch)
    print("API Server (with Orchestrator) starting on http://127.0.0.1:8000 ...")

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
