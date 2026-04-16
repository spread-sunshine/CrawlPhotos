# -*- coding: utf-8 -*-
"""
WeChat Official Account (MP) template message notifier.
微信通知模块 - 通过公众号模板消息推送通知.

Supports:
    - New target photo found notifications (template message)
    - Error/exception alerts (template message)
    - Daily summary reports (optional scheduled)

Config (from config.yaml):
    notification:
        enabled: true/false
        type: "wechat"
        wechat:
            app_id: "wx..."
            app_secret: "..."
            template_id_new_photo: "template_id_1"
            template_id_error: "template_id_2"
            template_id_summary: "template_id_3"
            receiver_openid: "oXXXXX"
        notify_on_new_photo: true
        notify_on_error: true
        daily_summary: true
        summary_time: "21:00"

API Reference:
    - Get access_token: https://api.weixin.qq.com/cgi-bin/token
    - Send template: https://api.weixin.qq.com/cgi-bin/message/template/send
"""

import logging
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional

import aiohttp

from app.config.logging_config import get_logger

logger = get_logger(__name__)

# WeChat MP API endpoints
_WECHAT_TOKEN_URL = (
    "https://api.weixin.qq.com/cgi-bin/token"
    "?grant_type=client_credential"
    "&appid={app_id}&secret={app_secret}"
)
_WECHAT_TEMPLATE_SEND_URL = (
    "https://api.weixin.qq.com/cgi-bin/"
    "message/template/send?access_token={token}"
)


class WeChatNotifier:
    """
    WeChat Official Account template message sender.

    Sends notifications via WeChat MP template messages.
    Manages access_token lifecycle automatically.
    """

    # Token cache
    _access_token: str = ""
    _token_expire_at: float = 0.0

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        template_id_new_photo: str = "",
        template_id_error: str = "",
        template_id_summary: str = "",
        receiver_openid: str = "",
        enabled: bool = False,
        notify_on_new_photo: bool = True,
        notify_on_error: bool = True,
        daily_summary: bool = False,
        summary_time: str = "21:00",
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._tmpl_new_photo = template_id_new_photo
        self._tmpl_error = template_id_error
        self._tmpl_summary = template_id_summary
        self._receiver_openid = receiver_openid
        self._enabled = enabled
        self._notify_new = notify_on_new_photo
        self._notify_error = notify_on_error
        self._daily_summary = daily_summary
        self._summary_time = summary_time

    @property
    def is_enabled(self) -> bool:
        """Check if notifier is properly configured."""
        return (
            self._enabled
            and bool(self._app_id)
            and bool(self._app_secret)
            and bool(self._receiver_openid)
        )

    async def _get_access_token(self) -> str:
        """Get or refresh access_token with caching."""
        import time

        now = time.time()
        if self._access_token and now < self._token_expire_at:
            return self._access_token

        url = _WECHAT_TOKEN_URL.format(
            app_id=self._app_id,
            app_secret=self._app_secret,
        )
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    result = await resp.json()
                    errcode = result.get("errcode", 0)
                    if errcode != 0:
                        logger.error(
                            "WeChat get token failed: %s",
                            result.get("errmsg", ""),
                        )
                        return ""
                    token = result.get("access_token", "")
                    expires_in = result.get(
                        "expires_in", 7200,
                    )
                    # Refresh 5 minutes early
                    self._access_token = token
                    self._token_expire_at = (
                        now + expires_in - 300
                    )
                    logger.debug(
                        "WeChat access_token refreshed, "
                        "expires in %ds",
                        expires_in,
                    )
                    return token
        except Exception as e:
            logger.error(
                "Failed to get WeChat token: %s", e,
            )
            return ""

    async def _send_template(
        self,
        template_id: str,
        data: Dict[str, Any],
        url: str = "",
    ) -> bool:
        """Send a template message to the configured receiver."""
        token = await self._get_access_token()
        if not token:
            logger.error(
                "Cannot send template: no access_token",
            )
            return False

        api_url = _WECHAT_TEMPLATE_SEND_URL.format(
            token=token,
        )
        payload: Dict[str, Any] = {
            "touser": self._receiver_openid,
            "template_id": template_id,
            "data": data,
        }
        if url:
            payload["url"] = url

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    api_url, json=payload,
                ) as resp:
                    result = await resp.json()
                    errcode = result.get("errcode", -1)
                    if errcode != 0:
                        logger.warning(
                            "WeChat template send error: "
                            "%s (errcode=%d)",
                            result.get("errmsg", ""),
                            errcode,
                        )
                        # Invalid token, clear cache
                        if errcode in (40001, 40014, 42001):
                            self._access_token = ""
                            self._token_expire_at = 0.0
                        return False
                    msg_id = result.get("msgid", 0)
                    logger.info(
                        "WeChat template sent OK, "
                        "msgid=%d",
                        msg_id,
                    )
                    return True
        except Exception as e:
            logger.error(
                "Failed to send WeChat template: %s", e,
            )
            return False

    async def notify_new_photo(
        self,
        photo_id: str,
        target_name: str,
        confidence: float,
        stored_path: str = "",
    ) -> bool:
        """Send notification when new target photo found."""
        if not (self.is_enabled and self._notify_new):
            return True
        if not self._tmpl_new_photo:
            logger.warning(
                "template_id_new_photo not configured, "
                "skipping new photo notification",
            )
            return True

        data = {
            "first": {
                "value": f"发现目标照片！",
                "color": "#173177",
            },
            "keyword1": {
                "value": target_name,
                "color": "#173177",
            },
            "keyword2": {
                "value": photo_id[:16],
                "color": "#173177",
            },
            "keyword3": {
                "value": f"{confidence:.1%}",
                "color": "#173177",
            },
            "keyword4": {
                "value": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S",
                ),
                "color": "#173177",
            },
            "remark": {
                "value": (
                    f"存储路径: {stored_path}"
                    if stored_path else ""
                ),
                "color": "#999999",
            },
        }
        return await self._send_template(
            self._tmpl_new_photo, data,
        )

    async def notify_error(
        self,
        error_msg: str,
        context: str = "",
        photo_id: str = "",
    ) -> bool:
        """Send error alert via template message."""
        if not (self.is_enabled and self._notify_error):
            return True
        if not self._tmpl_error:
            logger.warning(
                "template_id_error not configured, "
                "skipping error notification",
            )
            return True

        remark_parts = []
        if context:
            remark_parts.append(f"上下文: {context}")
        if photo_id:
            remark_parts.append(f"照片ID: {photo_id}")

        data = {
            "first": {
                "value": "系统异常告警",
                "color": "#FF0000",
            },
            "keyword1": {
                "value": error_msg[:50],
                "color": "#173177",
            },
            "keyword2": {
                "value": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S",
                ),
                "color": "#173177",
            },
            "remark": {
                "value": "\n".join(remark_parts),
                "color": "#999999",
            },
        }
        return await self._send_template(
            self._tmpl_error, data,
        )

    async def send_daily_summary(
        self,
        date_str: str,
        total_discovered: int,
        total_target_found: int,
        total_stored: int,
        total_failed: int,
        run_duration_seconds: float = 0.0,
    ) -> bool:
        """Send daily execution summary report."""
        if not (self.is_enabled and self._daily_summary):
            return True
        if not self._tmpl_summary:
            logger.warning(
                "template_id_summary not configured, "
                "skipping summary notification",
            )
            return True

        duration_min = run_duration_seconds / 60
        data = {
            "first": {
                "value": f"每日运行报告 ({date_str})",
                "color": "#173177",
            },
            "keyword1": {
                "value": str(total_discovered),
                "color": "#173177",
            },
            "keyword2": {
                "value": str(total_target_found),
                "color": "#173177",
            },
            "keyword3": {
                "value": str(total_stored),
                "color": "#173177",
            },
            "keyword4": {
                "value": str(total_failed),
                "color": "#173177",
            },
            "keyword5": {
                "value": f"{duration_min:.1f} 分钟",
                "color": "#173177",
            },
            "remark": {
                "value": (
                    f"今日发现 {total_target_found} 张"
                    f"目标照片！"
                    if total_target_found > 0
                    else "今日未发现新照片"
                ),
                "color": (
                    "#FF0000"
                    if total_target_found > 0
                    else "#999999"
                ),
            },
        }
        return await self._send_template(
            self._tmpl_summary, data,
        )

    async def send_custom_message(
        self,
        template_id: str,
        data: Dict[str, Any],
        url: str = "",
    ) -> bool:
        """Send arbitrary template message."""
        if not self.is_enabled:
            return True
        return await self._send_template(
            template_id, data, url,
        )


def create_notifier_from_config(config: dict) -> WeChatNotifier:
    """Factory: create WeChat notifier from config dict."""
    notif_cfg = config.get("notification", {})
    wechat_cfg = notif_cfg.get("wechat", {})
    return WeChatNotifier(
        app_id=wechat_cfg.get("app_id", ""),
        app_secret=wechat_cfg.get("app_secret", ""),
        template_id_new_photo=wechat_cfg.get(
            "template_id_new_photo", "",
        ),
        template_id_error=wechat_cfg.get(
            "template_id_error", "",
        ),
        template_id_summary=wechat_cfg.get(
            "template_id_summary", "",
        ),
        receiver_openid=wechat_cfg.get(
            "receiver_openid", "",
        ),
        enabled=notif_cfg.get("enabled", False),
        notify_on_new_photo=notif_cfg.get(
            "notify_on_new_photo", True,
        ),
        notify_on_error=notif_cfg.get(
            "notify_on_error", True,
        ),
        daily_summary=notif_cfg.get(
            "daily_summary", False,
        ),
        summary_time=notif_cfg.get(
            "summary_time", "21:00",
        ),
    )
