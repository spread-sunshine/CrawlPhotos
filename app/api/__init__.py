# -*- coding: utf-8 -*-
"""
API Service package.
API服务模块 - FastAPI REST接口.
"""

from app.api.server import create_app, start_api_server

__all__ = [
    "create_app",
    "start_api_server",
]
