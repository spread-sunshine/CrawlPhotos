"""
QQ相册收集机器人
使用NoneBot2框架监听群消息中的图片
"""

import nonebot
from nonebot import on_message, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.permission import GROUP
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

# 初始化 NoneBot
nonebot.init()

# 配置
OUTPUT_DIR = Path("data/collected_photos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 图片收集器
class PhotoCollector:
    def __init__(self):
        self.collected_count = 0
        self.session_photos = {}  # {group_id: [photo_urls]}
        
    async def download_image(self, url: str, group_id: int) -> Optional[str]:
        """下载图片到本地"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    # 生成文件名
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"group_{group_id}_{timestamp}_{self.collected_count}.jpg"
                    filepath = OUTPUT_DIR / filename
                    
                    # 保存文件
                    filepath.write_bytes(response.content)
                    self.collected_count += 1
                    return str(filepath)
        except Exception as e:
            print(f"Download failed: {e}")
        return None

collector = PhotoCollector()

# 监听群消息中的图片
photo_watcher = on_message(permission=GROUP, priority=5)


@photo_watcher.handle()
async def handle_photo(event: GroupMessageEvent):
    """处理群消息，提取图片"""
    message = event.message
    
    # 检查消息是否包含图片
    for segment in message:
        if segment.type == "image":
            # 获取图片URL
            image_url = segment.data.get("url", "")
            if image_url:
                print(f"[收到图片] 群: {event.group_id}, URL: {image_url[:50]}...")
                
                # 下载图片
                filepath = await collector.download_image(image_url, event.group_id)
                if filepath:
                    print(f"[保存成功] -> {filepath}")

# 状态查询命令
status_cmd = on_command("相册状态", permission=GROUP)


@status_cmd.handle()
async def show_status(event: GroupMessageEvent):
    """查看收集状态"""
    await status_cmd.finish(
        Message([
            MessageSegment.text("=== QQ相册收集状态 ===\n"),
            MessageSegment.text(f"本次运行已收集: {collector.collected_count} 张图片\n"),
            MessageSegment.text(f"保存目录: {OUTPUT_DIR}\n"),
            MessageSegment.text("\n提示: 群内发送的图片会被自动收集")
        ])
    )


# 导出命令
export_cmd = on_command("导出相册", permission=GROUP)


@export_cmd.handle()
async def export_album(event: GroupMessageEvent):
    """导出收集的图片到指定目录"""
    # 获取命令参数
    args = str(event.message).strip()
    
    if args:
        export_path = Path(args)
    else:
        # 默认导出到项目data目录
        export_path = Path("data/qq_exports")
    
    export_path.mkdir(parents=True, exist_ok=True)
    
    # 复制文件
    import shutil
    count = 0
    for photo in OUTPUT_DIR.glob("*.jpg"):
        shutil.copy(photo, export_path / photo.name)
        count += 1
    
    await export_cmd.finish(
        Message([
            MessageSegment.text(f"导出完成!\n"),
            MessageSegment.text(f"共导出 {count} 张图片\n"),
            MessageSegment.text(f"保存位置: {export_path}")
        ])
    )


# 帮助命令
help_cmd = on_command("相册帮助", permission=GROUP)


@help_cmd.handle()
async def show_help(event: GroupMessageEvent):
    """显示帮助信息"""
    help_text = """
=== QQ相册收集机器人 ===

命令列表：
1. /相册状态 - 查看收集状态
2. /导出相册 [目录] - 导出收集的图片
3. /相册帮助 - 显示此帮助

使用说明：
- 机器人会自动收集群内发送的所有图片
- 图片保存在 data/collected_photos 目录
- 需要机器人有查看消息权限
    """
    await help_cmd.finish(Message(help_text.strip()))


if __name__ == "__main__":
    nonebot.run()
