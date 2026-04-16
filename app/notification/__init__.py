# -*- coding: utf-8 -*-
"""
Notification package init.
通知模块入口.
"""

from app.notification.wechat import (
    WeChatNotifier,
    create_notifier_from_config,
)

__all__ = [
    "WeChatNotifier",
    "create_notifier_from_config",
]
