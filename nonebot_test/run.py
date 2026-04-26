"""
NoneBot2 启动脚本
替代 nb run 命令
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

import nonebot
from nonebot import run

if __name__ == "__main__":
    # 初始化 NoneBot
    nonebot.init(
        host="127.0.0.1",
        port=18080
    )
    
    # 启动机器人
    print("=" * 50)
    print("QQ相册收集机器人启动中...")
    print("=" * 50)
    print("WebSocket 连接地址: ws://127.0.0.1:3080")
    print("HTTP 服务端口: 18080")
    print("等待 LLOneBot 连接...")
    print()
    
    # 运行
    run()
