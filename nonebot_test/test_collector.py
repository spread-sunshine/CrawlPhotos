"""
NoneBot2 QQ相册收集机器人 - 独立测试模块

无需QQ客户端即可测试机器人的核心功能
模拟接收图片消息进行测试
"""

import asyncio
from pathlib import Path
from datetime import datetime
import httpx


class PhotoCollector:
    """图片收集器核心逻辑"""
    
    def __init__(self, output_dir: str = "data/collected_photos"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.collected_count = 0
        self.log = []
        
    def log_event(self, event_type: str, message: str):
        """记录事件"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{event_type}] {message}"
        self.log.append(log_entry)
        print(log_entry)
        
    async def download_image(self, url: str, group_id: int = 0) -> bool:
        """下载图片到本地"""
        try:
            self.log_event("DOWNLOAD", f"开始下载: {url[:60]}...")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                
                if response.status_code == 200:
                    # 生成文件名
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"group_{group_id}_{timestamp}_{self.collected_count}.jpg"
                    filepath = self.output_dir / filename
                    
                    # 保存文件
                    filepath.write_bytes(response.content)
                    self.collected_count += 1
                    
                    self.log_event("SUCCESS", f"已保存: {filename} ({len(response.content)} bytes)")
                    return True
                else:
                    self.log_event("ERROR", f"下载失败: HTTP {response.status_code}")
                    return False
                    
        except Exception as e:
            self.log_event("ERROR", f"下载异常: {str(e)}")
            return False
            
    def get_status(self) -> dict:
        """获取收集状态"""
        return {
            "total_collected": self.collected_count,
            "output_dir": str(self.output_dir),
            "recent_logs": self.log[-10:]  # 最近10条日志
        }
        
    def export_to_directory(self, target_dir: str) -> int:
        """导出收集的图片到指定目录"""
        import shutil
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for photo in self.output_dir.glob("*.jpg"):
            shutil.copy(photo, target / photo.name)
            count += 1
            
        return count


async def simulate_group_message(collector: PhotoCollector):
    """模拟接收群消息（测试用）"""
    
    print("\n" + "="*50)
    print("模拟测试：处理群消息中的图片")
    print("="*50)
    
    # 模拟消息类型
    message_types = [
        {
            "type": "image",
            "data": {"url": "https://example.com/test1.jpg"}
        },
        {
            "type": "text", 
            "data": {"text": "这是一段文字消息"}
        },
        {
            "type": "image",
            "data": {"url": "https://example.com/test2.jpg"}
        }
    ]
    
    for i, msg in enumerate(message_types):
        print(f"\n--- 消息 {i+1} ---")
        
        if msg["type"] == "image":
            # 模拟图片消息处理
            image_url = msg["data"]["url"]
            print(f"[模拟] 收到图片消息")
            print(f"[模拟] 提取URL: {image_url}")
            
            # 由于是示例URL，实际下载会失败
            # 这里我们跳过实际下载，只演示流程
            collector.log_event("SIMULATE", f"图片处理流程完成 (URL: {image_url[:40]}...)")
            
        elif msg["type"] == "text":
            print(f"[模拟] 收到文本消息: {msg['data']['text']}")
            
    print("\n" + "="*50)
    print("模拟测试完成")
    print("="*50)


async def test_collector():
    """测试收集器功能"""
    
    print("\n" + "#"*60)
    print("# NoneBot2 QQ相册收集机器人 - 功能测试")
    print("#"*60)
    
    # 初始化收集器
    collector = PhotoCollector()
    
    # 1. 测试状态查询
    print("\n[测试 1] 状态查询")
    status = collector.get_status()
    print(f"  收集数量: {status['total_collected']}")
    print(f"  输出目录: {status['output_dir']}")
    
    # 2. 测试事件日志
    print("\n[测试 2] 事件日志")
    collector.log_event("TEST", "测试日志记录功能")
    collector.log_event("INFO", "这是一条信息日志")
    collector.log_event("WARN", "这是一条警告日志")
    
    # 3. 模拟处理消息
    await simulate_group_message(collector)
    
    # 4. 导出功能测试
    print("\n[测试 3] 导出功能")
    export_dir = "data/test_exports"
    count = collector.export_to_directory(export_dir)
    print(f"  导出文件数: {count}")
    print(f"  导出目录: {export_dir}")
    
    # 最终状态
    print("\n" + "="*50)
    print("最终状态:")
    status = collector.get_status()
    print(f"  总收集数: {status['total_collected']}")
    print(f"  输出目录: {status['output_dir']}")
    print("="*50)
    
    return collector


def main():
    """主函数"""
    print("\n[NoneBot2 QQ相册收集机器人测试]")
    print("-" * 40)
    
    # 运行异步测试
    collector = asyncio.run(test_collector())
    
    print("\n" + "-"*40)
    print("测试完成!")
    print("\n下一步:")
    print("1. 配置 .env 文件，设置QQ机器人连接参数")
    print("2. 安装 LLOneBot 或 go-cqhttp")
    print("3. 运行 'nb run' 启动机器人")
    print("-"*40)


if __name__ == "__main__":
    main()
