# NoneBot2 QQ相册收集机器人

基于 NoneBot2 框架的 QQ 群相册照片自动收集工具。

## 功能特性

- 自动监听群消息中的图片
- 自动下载并保存图片到本地
- 支持多个群同时收集
- 提供命令查询收集状态
- 支持导出收集的图片

## 项目结构

```
onebot_test/
├── bot.py              # 机器人主程序
├── test_collector.py   # 独立测试模块
├── pyproject.toml      # 项目配置
├── .env                # 环境变量配置
└── data/               # 数据目录
    └── collected_photos/  # 图片保存位置
```

## 安装依赖

```bash
# 核心依赖
pip install nonebot2 nonebot-adapter-onebot

# 可选依赖
pip install httpx   # 图片下载
```

## 完整部署步骤

### 步骤 1：安装 LLOneBot（推荐）

LLOneBot 是一个 QQ 机器人客户端，可以让你的 QQ 号作为机器人使用。

1. 下载 LLOneBot
   - 官网: https://github.com/LLOneBot/LLOneBot
   - 或使用NapCat: https://github.com/NapNeko/NapCatQQ

2. 配置 LLOneBot
   - 登录你的 QQ 号
   - 开启 WebSocket 服务
   - 记录 WebSocket 地址（如 `ws://127.0.0.1:3001`）

### 步骤 2：配置 NoneBot2

编辑 `.env` 文件：

```env
# LLOneBot WebSocket 地址
ONEBOT_WS_URLS=["ws://127.0.0.1:3001"]

# 或使用反向 WebSocket
ONEBOT_WS_REVERSE_URLS=["ws://127.0.0.1:8080/cqhttp"]
```

### 步骤 3：配置 pyproject.toml

```toml
[tool.nonebot]
plugins = []
adapters = [{ name = "onebot11", module = "nonebot.adapters.onebot" }]
```

### 步骤 4：启动机器人

```bash
# 使用 nb-cli 启动
nb run

# 或直接运行
python bot.py
```

## 使用命令

在 QQ 群中发送以下命令：

| 命令 | 说明 |
|------|------|
| `/相册状态` | 查看收集统计 |
| `/导出相册` | 导出图片到 data/qq_exports |
| `/导出相册 目录名` | 导出到指定目录 |
| `/相册帮助` | 显示帮助信息 |

## 工作原理

```
┌─────────────┐    WebSocket    ┌─────────────────┐
│   LLOneBot  │ ────────────── │   NoneBot2      │
│   (QQ客户端)  │                │   机器人框架     │
└─────────────┘                └────────┬────────┘
                                       │
                                       │ on_message
                                       ▼
                              ┌─────────────────┐
                              │  PhotoCollector │
                              │  图片收集器      │
                              └────────┬────────┘
                                       │
                                       │ 保存
                                       ▼
                              ┌─────────────────┐
                              │  本地目录        │
                              │  data/photos    │
                              └─────────────────┘
```

## 已知问题

1. **图片URL有时效性**: QQ图片URL可能在一定时间后失效，需要及时下载保存
2. **权限要求**: 机器人需要能够查看群消息
3. **频率限制**: 避免过于频繁的下载请求

## 与 CrawlPhotos 集成

收集的图片可以与 CrawlPhotos 配合使用：

1. 修改 `config.yaml`：
```yaml
source:
  type: local_directory
  local_directory:
    path: onebot_test/data/collected_photos
    recursive: true
```

2. 运行 CrawlPhotos 处理收集的照片：
```bash
python main.py
```

## 故障排除

### 1. 连接失败
```
Error: Cannot connect to LLOneBot
```
解决：检查 LLOneBot 是否运行，WebSocket 地址是否正确

### 2. 消息未处理
解决：检查机器人是否已加入群聊，且有消息查看权限

### 3. 图片下载失败
解决：某些图片URL有时效性，建议实时下载保存
