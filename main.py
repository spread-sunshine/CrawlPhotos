# -*- coding: utf-8 -*-
"""
Baby Photos Auto-Filter Tool - Main Entry Point.
宝宝照片自动筛选工具 - 主程序入口.

Usage:
    python main.py --run                   # Run once
    python main.py --run --days 3           # Scan last 3 days
    python main.py --run --date 2026-04-15  # Specific date
    python main.py --schedule               # Start scheduler mode
    python main.py --setup                 # Configuration wizard
    python main.py --status                # Show system status
    python main.py --help                  # Show help
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Centralize bytecode cache to single directory
# Option A: Disable .pyc generation entirely
sys.dont_write_bytecode = True

from app.config.logging_config import setup_logging, get_logger
from app.config.settings import Settings, ConfigError
from app.database.db import Database
from app.face_recognition.facade import FaceRecognizerFacade
from app.face_recognition.models import TargetConfig
from app.crawler.qq_album_crawler import QQAlbumCrawler
from app.preprocessor.image_pipeline import (
    ImagePreprocessor, PreprocessConfig,
)
from app.storage.local_storage import StorageManager
from app.orchestrator import Orchestrator
from app.triggers.scheduler import (
    ManualTrigger,
    ScheduledTrigger,
    EventTrigger,
)
from app.models.photo import TriggerType

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Baby Photos Auto-Filter Tool - "
                    "Automatically collect and filter your "
                    "child's photos from QQ group albums.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --run                          Run pipeline once
  python main.py --run --days 7                 Scan last 7 days
  python main.py --schedule                     Start scheduled mode
  python main.py --schedule --cron "0 */30 * *" Custom cron schedule
  python main.py --status                       Show system status
        """,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--run",
        action="store_true",
        help="Execute the pipeline once and exit.",
    )
    mode_group.add_argument(
        "--schedule",
        action="store_true",
        help="Start scheduler daemon mode.",
    )
    mode_group.add_argument(
        "--status",
        action="store_true",
        help="Show system status and recent run history.",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of past days to scan (with --run).",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Specific date to scan YYYY-MM-DD (with --run).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml (default: config/config.yaml).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        help="Override log level from config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without making changes.",
    )

    return parser.parse_args()


async def create_components(settings: Settings, db: Database):
    """
    Initialize all application components based on settings.

    Returns:
        Tuple of (orchestrator, crawler) for use by triggers.
    """
    log_level = settings.get("logging.level", "INFO")
    setup_logging(log_level=log_level)

    # Face recognition facade
    face_config = settings.get_section("face_recognition")
    recognizer = FaceRecognizerFacade(face_config)

    # Initialize targets
    targets = _load_targets(settings)
    if targets:
        await recognizer.initialize(targets)

    # Crawler
    crawler = QQAlbumCrawler(
        group_id=settings.require("qq.group.group_id"),
        cookies_file=settings.get(
            "qq.group.cookies_file",
            "data/qq_cookies.txt",
        ),
    )

    # Preprocessor
    preprocess_cfg = PreprocessConfig(
        max_width=2048,
        max_height=2048,
        jpeg_quality=85,
    )
    preprocessor = ImagePreprocessor(preprocess_cfg)

    # Storage
    storage_root = settings.get(
        "storage.root_directory", "./output"
    )
    storage = StorageManager(root_directory=storage_root)

    # Orchestrator
    orchestrator = Orchestrator(
        settings=settings,
        database=db,
        recognizer=recognizer,
        crawler=crawler,
        preprocessor=preprocessor,
        storage_manager=storage,
    )

    return orchestrator, crawler


def _load_targets(settings: Settings) -> list:
    """Load target person configurations from settings."""
    targets_config = settings.get(
        "face_recognition.targets", []
    )
    targets = []

    for tc in targets_config:
        ref_dir = tc.get("reference_photos_dir", "")
        ref_paths = []
        if ref_dir:
            ref_dir_path = Path(ref_dir)
            if ref_dir_path.exists():
                exts = {".jpg", ".jpeg", ".png", ".webp"}
                ref_paths = [
                    p for p in sorted(ref_dir_path.iterdir())
                    if p.suffix.lower() in exts
                ]

        target = TargetConfig(
            name=tc.get("name", "Unknown"),
            reference_photo_paths=ref_paths,
            min_confidence=tc.get("min_confidence", 0.80),
            enabled=tc.get("enabled", True),
        )
        targets.append(target)
        logger.info(
            "Loaded target: %s (%d reference photos)",
            target.name,
            len(ref_paths),
        )

    return targets


async def cmd_run(args: argparse.Namespace, db: Database) -> None:
    """Handle --run mode: execute pipeline once."""
    settings = Settings.load(
        Path(args.config) if args.config else None
    )

    orchestrator, crawler = await create_components(
        settings, db
    )

    trigger_opts: dict = {}
    if args.days:
        trigger_opts["scan_days_back"] = args.days
    if args.date:
        trigger_opts["specific_date"] = args.date

    try:
        run = await orchestrator.execute(
            TriggerType.MANUAL, trigger_opts
        )
        print(f"\n{'='*50}")
        print(f"Pipeline completed!")
        print(f"  Run ID:       {run.run_id}")
        print(f"  Discovered:   {run.total_discovered} photos")
        print(f"  New:          {run.total_new} photos")
        print(f"  Target found: {run.total_contains_target} photos")
        print(f"  Stored:       {run.total_stored} photos")
        print(f"  Failed:       {run.total_failed} photos")
        print(f"  Duration:     {run.duration_seconds:.1f}s" if run.duration_seconds else "")
        print(f"{'='*50}\n")
    finally:
        await crawler.close()
        await orchestrator._recognizer.cleanup()


async def cmd_schedule(args: argparse.Namespace, db: Database) -> None:
    """Handle --schedule mode: run as daemon with scheduler."""
    settings = Settings.load(
        Path(args.config) if args.config else None
    )

    orchestrator, crawler = await create_components(
        settings, db
    )

    sched_config = settings.get_section("scheduler")
    scheduled_trigger = ScheduledTrigger(
        cron_expression=sched_config.get(
            "cron_expression", "0 */30 * * * *"
        ),
        startup_scan=sched_config.get("startup_scan", True),
        scan_days_back=sched_config.get("scan_days_back", 7),
    )

    # Define pipeline callback
    async def pipeline_callback(trigger_type: TriggerType, options: dict):
        await orchestrator.execute(trigger_type, options)

    # Start scheduler
    scheduled_trigger.start(pipeline_callback)

    logger.info("Scheduler running. Press Ctrl+C to exit.")

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        await shutdown_event.wait()
    finally:
        scheduled_trigger.stop()
        await crawler.close()
        await orchestrator._recognizer.cleanup()
        logger.info("Shutdown complete.")


async def cmd_status(db: Database) -> None:
    """Handle --status mode: show system status."""
    print("\n=== System Status ===\n")

    # Recent runs
    runs = db.get_recent_runs(5)
    if runs:
        print("Recent Runs:")
        print("-" * 70)
        for r in runs:
            status_icon = {
                "completed": "[OK]",
                "running":   "[>>]",
                "failed":    "[!!]",
            }.get(r["status"], "[??]")
            print(
                f"  {status_icon} {r['run_id'][:8]}... | "
                f"{r['trigger_type']:>10s} | "
                f"+{r['total_discovered']} | "
                f"new={r['total_new']} | "
                f"target={r['total_contains_target']} | "
                f"stored={r['total_stored']} | "
                f"fail={r['total_failed']}"
            )
        print()

    # Photo counts by status
    from app.models.photo import PhotoStatus
    statuses = [
        ("Pending", PhotoStatus.PENDING),
        ("Downloaded", PhotoStatus.DOWNLOADED),
        ("Recognized", PhotoStatus.RECOGNIZED),
        ("Completed", PhotoStatus.COMPLETED),
        ("Failed", PhotoStatus.FAILED),
        ("Skipped", PhotoStatus.SKIPPED),
    ]
    print("Photo Status Summary:")
    print("-" * 40)
    for label, st in statuses:
        count = db.count_by_status(st)
        print(f"  {label:<14s}: {count:>6d}")

    print()


def main() -> None:
    """Application entry point."""
    args = parse_args()

    # Initialize database (always needed)
    db = Database()
    db.initialize()

    try:
        if args.run:
            asyncio.run(cmd_run(args, db))
        elif args.schedule:
            asyncio.run(cmd_schedule(args, db))
        elif args.status:
            asyncio.run(cmd_status(db))
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        db.close()


if __name__ == "__main__":
    main()
