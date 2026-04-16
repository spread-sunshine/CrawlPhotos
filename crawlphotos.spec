# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for CrawlPhotos - Baby Photos Auto-Filter Tool.
宝宝照片自动筛选工具 - Windows exe 打包配置.

Usage:
    pyinstaller crawlphotos.spec
    # Or with clean build:
    pyinstaller --clean crawlphotos.spec

Output:
    dist/CrawlPhotos.exe (single-file executable)
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Project root
a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').absolute())],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('web', 'web'),
        ('data', 'data'),
    ],
    hiddenimports=[
        # Core app modules
        'app',
        'app.orchestrator',
        'app.config.settings',
        'app.config.logging_config',
        'app.config.setup_wizard',
        'app.database.db',
        'app.database.dedup',
        'app.models.photo',
        'app.crawler.qq_album_crawler',
        'app.face_recognition.facade',
        'app.face_recognition.interfaces',
        'app.face_recognition.models',
        'app.face_recognition.registry',
        'app.face_recognition.multi_target_handler',
        'app.face_recognition.reference_updater',
        'app.preprocessor.image_pipeline',
        'app.storage.local_storage',
        'app.storage.personal_album_uploader',
        'app.triggers.scheduler',
        'app.notification.wechat',
        'app.api.server',

        # Phase 4 new modules
        'app.core.metrics',
        'app.core.metrics_listener',
        'app.core.review_pool',

        # Face recognition providers
        'app.face_recognition.providers.tencent_cloud',
        'app.face_recognition.providers.baidu',
        'app.face_recognition.providers.insightface',
        'app.face_recognition.providers.no_op_provider',

        # Core infrastructure
        'app.core.event_bus',
        'app.core.events',
        'app.core.circuit_breaker',
        'app.core.cookie_monitor',
        'app.core.crawler_registry',
        'app.core.data_checker',
        'app.core.recognition_cache',
        'app.core.retry',
        'app.core.state_machine',
        'app.core.task_queue_persist',
        'app.core.upload_queue',

        # Third-party dependencies
        'PIL', 'PIL.Image', 'yaml', 'aiohttp', 'apscheduler',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'scipy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure, a.zipped_data, cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CrawlPhotos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add an .ico file here if desired
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CrawlPhotos',
)
