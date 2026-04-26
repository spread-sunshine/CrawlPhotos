"""
快速测试脚本 - 检查NoneBot2与LLOneBot连接状态
"""

import asyncio
import sys
sys.path.insert(0, '.')

import nonebot
from nonebot import init, get_adapters

print("=" * 50)
print("NoneBot2 + LLOneBot 连接测试")
print("=" * 50)

# 初始化 NoneBot
print("\n[1] 初始化 NoneBot...")
init()
print("    OK - NoneBot initialized")

# 检查适配器
print("\n[2] 检查适配器...")
adapters = get_adapters()
for adapter in adapters:
    print(f"    - {adapter.name}: {adapter}")
print(f"    共 {len(adapters)} 个适配器")

# 检查 WebSocket 连接配置
print("\n[3] 检查 WebSocket 配置...")
print("    LLOneBot 地址: ws://127.0.0.1:3080")

# 检查端口
import socket
print("\n[4] 检查 LLOneBot 端口...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('127.0.0.1', 3080))
sock.close()
if result == 0:
    print("    OK - LLOneBot 端口 3080 正在监听")
else:
    print("    WARNING - LLOneBot 端口 3080 未响应")

print("\n" + "=" * 50)
print("下一步: 运行 'python bot.py' 启动机器人")
print("       或使用 'nb run' (需要安装 nb-cli)")
print("=" * 50)
