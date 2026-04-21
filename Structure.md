# 宝宝照片自动筛选工具 - 系统结构与流程图

> 本文档从 PRD 中抽离所有架构流程图与代码结构描述，
> 便于开发者理解系统设计而不受需求文档篇幅干扰。

---

## 一、目录结构

```
CrawlPhotos/
├── main.py                          # 主程序入口 (CLI)
├── config/
│   └── config.yaml                  # 全局配置文件
├── data/
│   ├── crawl_photos.db              # SQLite主数据库
│   └── review_pending/              # 审核池临时文件
├── app/
│   ├── __init__.py                  # 包元数据 (version, author)
│   ├── orchestrator.py              # 编排引擎: 采集→下载→识别→存储 流水线
│   │
│   ├── api/                         # REST API 服务层
│   │   └── server.py                # FastAPI 应用 (手动触发/照片查询/统计/审核/指标导出)
│   │
│   ├── config/                      # 配置管理模块
│   │   ├── settings.py              # Settings 类: YAML加载+校验+环境变量解析
│   │   ├── logging_config.py        # loguru 日志初始化 (格式/轮转/级别)
│   │   └── setup_wizard.py          # --setup 模式: 7步交互式配置引导
│   │
│   ├── core/                        # 核心基础设施
│   │   ├── event_bus.py             # EventBus: 发布-订阅总线 (单例/线程安全)
│   │   ├── events.py                # EventType枚举 + 各Event data class定义
│   │   ├── task_queue_persist.py    # TaskQueueManager: SQLite持久化队列+状态机+DLQ
│   │   ├── state_machine.py         # TaskStatus状态机校验器
│   │   ├── circuit_breaker.py       # RateLimiter + CircuitBreaker + Fallback三级防护
│   │   ├── retry.py                 # RetryHandler: 指数退避重试
│   │   ├── metrics.py               # MetricsCollector/MetricsDB: Counter/Gauge/Histogram
│   │   ├── metrics_listener.py      # MetricsEventListener: EventBus自动指标采集
│   │   ├── review_pool.py           # ReviewPool: 双阈值人工审核池
│   │   ├── recognition_cache.py     # LRU内存缓存 + SQLite持久化识别结果缓存
│   │   ├── crawler_registry.py      # CrawlerRegistry: 采集器插件注册表+工厂
│   │   ├── cookie_monitor.py        # Cookie有效期检测+到期预警
│   │   ├── data_checker.py          # 数据一致性检查工具
│   │   └── upload_queue.py          # 个人相册上传重试队列
│   │
│   ├── crawler/                     # 相册采集模块
│   │   └── qq_album_crawler.py      # QQAlbumCrawler: QQ群相册Cookie模拟采集
│   │
│   ├── database/                    # 数据持久层
│   │   ├── db.py                    # Database: SQLite连接/建表/CRUD操作
│   │   └── dedup.py                 # 三层去重 (内存Set + SQLite + SHA256 Hash)
│   │
│   ├── face_recognition/            # 人脸识别引擎 (可插拔架构)
│   │   ├── interfaces.py            # IFaceRecognizer: 抽象基类(统一接口定义)
│   │   ├── models.py                # 数据模型: BoundingBox/FaceDetection/RecognitionResult/TargetConfig/ProviderInfo
│   │   ├── exceptions.py            # 异常体系: FaceRecognizerError 及子类
│   │   ├── registry.py              # FaceRecognizerRegistry: 单例注册表+工厂方法
│   │   ├── facade.py                # FaceRecognizerFacade: 门面类(业务层唯一入口)
│   │   ├── multi_target_handler.py  # 多目标人物支持 (多孩子场景)
│   │   ├── reference_updater.py     # 参考照片自动更新机制
│   │   └── providers/               # Provider 实现
│   │       ├── tencent_cloud.py     # TencentCloudProvider (默认, 云端API)
│   │       ├── baidu.py             # BaiduProvider (云端API)
│   │       ├── insight_face.py      # InsightFaceLocalProvider (本地模型,离线)
│   │       └── no_op_provider.py    # NoOpRecognizer (测试用空实现)
│   │
│   ├── models/                      # 领域模型
│   │   ├── models.py                # 基础模型导出
│   │   └── photo.py                 # PhotoInfo/DailyMetadata/ProcessedPhoto/TaskRun 等
│   │
│   ├── notification/                # 通知模块
│   │   └── wechat.py                # WeChatNotifier: 微信通知推送
│   │
│   ├── preprocessor/                # 图片预处理管道
│   │   └── image_pipeline.py        # ImagePreprocessor: EXIF校正/格式转换/缩放/压缩
│   │
│   ├── storage/                     # 存储管理
│   │   ├── local_storage.py         # StorageManager: 按月归档存储 + metadata.json生成
│   │   └── personal_album_uploader.py # PersonalAlbumUploader: 个人QQ相册上传
│   │
│   └── triggers/                    # 触发调度
│       └── scheduler.py            # ManualTrigger / ScheduledTrigger(APScheduler) / EventTrigger
│
├── web/                             # 前端 Web UI (Vue3 + TDesign + Vite)
│   ├── index.html                   # 入口HTML
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.js                  # Vue应用入口
│       ├── App.vue                  # 根组件: TDesign Layout (Header菜单 + RouterView)
│       ├── api/index.js             # API客户端封装 (fetch + 路由)
│       └── views/
│           ├── HomeView.vue         # 照片墙首页 (瀑布流展示)
│           ├── CalendarView.vue     # 日历视图 (月历热力图)
│           ├── StatsView.vue        # 统计面板 (KPI指标图表)
│           └── ReviewView.vue       # 审核池 (待审核照片列表+审批操作)
│
├── build.bat                        # Windows 打包脚本 (PyInstaller)
├── crawlphotos.spec                 # PyInstaller 打包配置
├── requirements.txt                 # Python依赖
├── README.md                        # 使用说明文档
└── PRD_宝宝照片自动筛选工具.md       # 产品需求文档
```

---

## 二、核心架构图

### 2.1 整体分层架构

```
用户层: CLI命令行 / 本地文件夹 / Web浏览器(H5) / 微信通知 / 微信小程序(V2.0)
           │
接入层: FastAPI REST Server (V1.x可选, V2.0核心)
           │
应用层: 宝宝照片管家主程序
  ├── 调度引擎(3种触发模式)
  ├── 配置管理器 / 日志服务 / 通知服务
  ├── 编排层(去重+幂等)
  ├── 相册采集器 / 人脸识别引擎 / 存储管理器
           │
外部依赖层: QQ群相册(Cookie) / 腾讯云AI API / 本地文件系统+SQLite
```

### 2.2 数据流端到端

```
QQ群相册 --[①轮询新照片]--> 相册采集器 --[②下载]--> 临时缓冲
                                              |
                                         [③人脸检测]
                                              |
                                        人脸识别引擎
                                              |
                                    [④返回识别结果]
                                              |
                              ┌───────────────┤
                        是   ▼               ▼   否
                   [⑤按月归档]      [丢弃标记]
                        |
                  [⑥可选:上传个人相册]
                        |
                  [⑦记录状态到SQLite]
```

### 2.3 编排流水线 (Orchestrator)

```
Trigger
  │
  v
[Discover Photos] --> [Dedup Check]
  |                      |
  v                      v (new only)
[Download Photos] --> [Compute Hash]
  |                      |
  v                      v (unique hash)
[Preprocess Images]      |
  |                      v
[Face Recognition]  [Skip Duplicate]
  |
  +---> [Contains Target?] --Yes--> [Store Locally]
  |                                    |
  +---> No/Skip                       v
                                 [Record Result]
                                    |
                                    v
                               [Optional Upload]
```

### 2.4 触发模式总览

```
┌──────────────────────────────────────────────────────┐
│                    触发调度中心                        │
├──────────┬──────────────┬───────────────────────────┤
│ 模式A    │   模式B      │        模式C              │
│ 事件触发 │  定时触发     │      手动触发             │
│          │              │                           │
│ QQ消息   │ Cron表达式    │ CLI / Web API / 托盘菜单  │
│ 监听     │ 工作日30min  │ python main.py --run     │
│ 实时响应 │ 周末2h       │ POST /api/v1/tasks/trigger│
└──────────┴──────────────┴───────────────────────────┘
           │              │               │
           └──────────────┴───────────────┘
                          │
                    统一入队(去重)
```

---

## 三、可插拔架构

### 3.1 人脸识别 Provider 架构

```
调用方 (业务层: Orchestrator / API)
    │
    ▼
FaceRecognizerFacade (门面) ← 唯一入口,不关心实现
    │ 读config → 选provider → 工厂创建 → 异常统一包装
    ▼
FaceRecognizerRegistry (注册表+工厂)
    │ ProviderType -> Class 映射表
    ▼
IFaceRecognizer (抽象基类/接口)
    │
    ├──────────────┬──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
TencentCloud   Baidu        InsightFace    FacePlus    NoOp(测试)
Provider       Provider     LocalProvider  Provider    Provider
(云端API)      (云端API)    (本地模型)     (云端API)

切换方式: config.yaml 中修改 face_recognition.provider 字段值即可
扩展方式: 新建文件继承IFaceRecognizer → 注册到Registry → 改配置
运行时切换: facade.switch_provider("insight_face_local", {...})
```

**IFaceRecognizer 接口方法**:

| 方法 | 说明 |
|------|------|
| `initialize(targets)` | 初始化引擎，预加载目标特征库 |
| `health_check()` | 服务可用性健康检查 |
| `detect_faces(image_path)` | 人脸检测(不含识别比对) |
| `recognize(image_path)` | 核心: 检测+特征提取+1:N搜索 |
| `add_reference_photos(name, paths)` | 添加/更新参考照片 |
| `remove_target(name)` | 移除目标人物 |
| `list_targets()` | 列举已注册目标及状态 |
| `batch_recognize(paths, concurrency)` | 批量识别(可选优化) |
| `cleanup()` | 资源清理 |

**人脸识别数据模型**:

| 模型 | 用途 |
|------|------|
| `ProviderType` (Enum) | TENCENT_CLOUD / BAIDU / FACE_PLUS / INSIGHT_FACE_LOCAL / ALIYUN / CUSTOM |
| `BoundingBox` (dataclass) | 人脸坐标框 x,y,width,height |
| `FaceDetection` (dataclass) | 单次检测结果 face_id/bounding_box/confidence |
| `RecognitionResult` (dataclass) | 完整结果: contains_target/target_matches/best_confidence |
| `TargetConfig` (dataclass) | 目标人物: name/reference_paths/min_confidence/enabled |
| `ProviderInfo` (dataclass) | Provider能力描述(是否本地/批处理支持/成本等) |

### 3.2 采集器 Crawler 可插拔架构

```
调用方 (Orchestrator)
    │
    ▼
CrawlerRegistry (注册表+工厂)
    ▼
IAlbumCrawler (统一接口)
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  ▼
CookieSimCrawler  LagrangeCoreCrawler  BrowserPluginCrawler
(默认: HTTP模拟)  (第三方协议)         (最稳定: 浏览器扩展)
稳定性中低          支持实时监听          需开发Chrome扩展
Cookie易过期       Token自动续期         直接使用登录态
```

**IAlbumCrawler 接口**: initialize / health_check / fetch_album_list / fetch_new_photos(since) / download_photo / cleanup

### 3.3 存储 Backend 可插拔抽象 (规划中)

```
IStorageBackend (统一接口)
    │
    ├── LocalStorage (当前MVP, 本地文件系统)
    ├── COSStorage   (腾讯云对象存储)
    ├── OSSStorage   (阿里云OSS)
    ├── S3Storage    (MinIO兼容)
    └── NASStorage   (SMB/NFS网络挂载)
```

---

## 四、事件总线拓扑 (EventBus)

```
  ┌──────────┐  PHOTO_DISCOVERED   ┌──────────┐
  │ 相册采集器│ ──────────────────→ │ EventBus │
  └──────────┘                     │  Router  │
  ┌──────────┐  DOWNLOADED         ├──────────┤
  │ 下载模块  │ ──────────────────→ │          │
  └──────────┘                     │          │
  ┌──────────┐  RECOGNIZED         │          ├──→ 存储管理器 (订阅 STORED)
  │识别引擎   │ ──────────────────→ │          ├──→ 上传服务  (订阅 UPLOADED)
  └──────────┘                     │          ├──→ 通知服务  (订阅 TARGET_FOUND)
                                   │          ├──→ Metrics   (订阅 ALL)
                                   │          ├──→ 审核池    (订阅 灰色区间)
                                   │          └──→ 审计日志  (订阅 ALL)
                                   └──────────┘
```

**EventType 枚举分类**:

| 分类 | 事件类型 |
|------|---------|
| **流水线生命周期** | PIPELINE_STARTED / COMPLETED / FAILED / STEP_STARTED / STEP_COMPLETED |
| **采集** | CRAWLER_PHOTO_DISCOVERED / CRAWL_COMPLETED / CRAWL_FAILED |
| **下载** | DOWNLOAD_STARTED / COMPLETED / FAILED / SKIPPED (dedup命中) |
| **识别** | RECOGNITION_STARTED / COMPLETED / FAILED / TARGET_FOUND / TARGET_NOT_FOUND |
| **存储** | PHOTO_STORED |
| **系统** | COOKIE_EXPIRING |

---

## 五、状态机与任务队列

### 5.1 任务队列状态机

```
                    ┌──────────────────────────────┐
                    │                              │
                    ▼                              │
  PENDING ──→ RUNNING ──→ SUCCESS (成功终结)
                  │
                  ▼
               FAILED ──┬──→ PENDING (重试,指数退避30s/60s/120s/240s)
                          │
                          └──→ DEAD_LETTER (重试耗尽,人工介入)

  PENDING ──→ SKIPPED (去重命中/不满足条件,直接终结)
  PENDING ──→ CANCELLED (用户取消,直接终结)
```

**TaskQueueManager 核心能力**:

- 原子入队: `INSERT OR IGNORE` 幂等，防重复入队
- 原子出队: `UPDATE WHERE status='PENDING'` 并发安全
- 崩溃恢复: `recover_stale_tasks()` 超时任务回退到PENDING
- 死信隔离: 重试耗尽自动移入dead_letter_queue表

### 5.2 照片全生命周期状态

```
PENDING → DOWNLOADING → DOWNLOADED → PREPROCESSING → RECOGNIZING
                                                          │
                                                    RECOGNIZED
                                                          │
                                          ┌───────────────┤
                                        是│               │否
                                          ▼               ▼
                                      STORING         FAILED/SKIPPED
                                          │
                                       STORED
                                          │
                                     UPLOADING (可选)
                                          │
                                       UPLOADED
                                          │
                                      COMPLETED
```

---

## 六、熔断器+限流+降级三级防护

```
请求 ──→ [Level 1: RateLimiter] ──→ [Level 2: CircuitBreaker] ──→ [Level 3: Fallback] ──→ Provider
              │ 令牌桶QPS控制              │ 三状态检测                     │ 优雅降级
              │ 超过则排队/429             │                               │
              ▼                           ▼                               ▼
                                   OPEN时快速失败                     返回缓存/切换Provider/跳过

CircuitBreaker 三状态流转:
  CLOSED(正常通行) ──[连续N次失败]──→ OPEN(快速失败,停止调用)
       ^                                       │
       │                                 [冷却期超时]
       │                                       ▼
       +────── HALF_OPEN(半开,试探放行) ←──────┘
                    │
              [试探成功 → 恢复CLOSED]
              [试探失败 → 回到OPEN]
```

**降级触发条件**: 熔断器打开 / 配额低于50 / API延迟>3s / 连续10次错误

---

## 七、图片预处理管道

```
原始照片(3-10MB, HEIC/WebP/BMP/JPEG等)
    │
    ▼
[① 格式验证与转换] ──→ HEIC/WebP/BMP → 统一转为JPEG
    │
    ▼
[② EXIF方向校正] ← 最关键! 解决手机拍照旋转90°/180°问题
    │
    ▼
[③ 尺寸智能缩放] ──→ 保持宽高比,不超过max_size (各Provider参数不同)
    │
    ▼
[④ 质量压缩] ──→ JPEG quality 85%, 视觉无损 (体积减少60-80%)
    │
    ▼
预处理后照片 → 送入识别引擎
```

**各Provider推荐参数**: 腾讯云1920x1080 / 百度2048x2048 / InsightFace 640x640

---

## 八、双阈值 + 人工审核池

```
识别置信度
  1.0 ┤
      │     ┌──────────────────┐
  0.92 ├─────┤  高置信区(自动通过)  │ ──→ 直接归档
      │     └──────────────────┘
      │     ┌──────────────────┐
  0.75 ├─────┤   灰色区间(审核池)   │ ──→ 进入ReviewPool等待人工确认
      │     └──────────────────┘
      │     ┌──────────────────┐
  0.00 ├─────┤  低置信区(默认丢弃)  │ ──→ 丢弃(或按no_face_action配置)
      │     └──────────────────┘
  0.0  ┤
```

**ReviewPool 特性**:
- 最大容量200张 (超出最早的自动通过)
- 48小时未审核自动通过 (保守策略)
- 审核理由枚举: LOW_CONFIDENCE / NO_FACE / EDGE_CASE / AMBIGUOUS_MATCH
- Web UI提供审核界面 (ReviewView.vue)

---

## 九、Metrics 指标体系

### 9.1 四种指标类型

| 类型 | 说明 | 示例指标 |
|------|------|---------|
| **Counter** | 单调递增计数器 | photos_processed_total / faces_detected_total / target_found_total / tasks_completed_total |
| **Gauge** | 可变数值快照 | api_quota_remaining / disk_usage_bytes / task_queue_pending / circuit_breaker_state |
| **Histogram** | 分布统计(分桶) | recognize_latency_sec / download_latency_sec / confidence_distribution |
| **Summary** | 分位数统计 | p50 / p95 / p99 延迟 |

### 9.2 可观测性链路

```
每次任务分配唯一TraceID: YYYYMMDD-HHmmss-{hex8}
    │
    ▼
贯穿所有日志条目和EventBus事件
    │
    ▼
增强健康检查端点 GET /api/v1/health
  返回各子系统状态: database / storage_disk / qq_crawler /
  face_recognizer / task_queue / event_bus / review_pool
  + metrics_snapshot 关键指标快照
```

**Prometheus导出**: HTTP端点输出 Prometheus Text Format，供Grafana读取。

---

## 十、Web前端结构

```
Vue3 SPA (Vite构建) + TDesign组件库

App.vue (根布局)
├── Header: TDesign Layout + 水平Menu
│   ├── 照片墙 (/)        → HomeView.vue    (瀑布流展示已筛选照片)
│   ├── 日历 (/calendar)  → CalendarView.vue (月历热力图视图)
│   ├── 统计 (/stats)     → StatsView.vue    (KPI面板+图表)
│   └── 审核池 (/review)  → ReviewView.vue   (待审核照片+通过/拒绝操作)
└── Content: <router-view />

API通信: web/src/api/index.js → fetch() → http://localhost:端口/api/v1/*
```

---

## 十一、异常体系

```
FaceRecognizerError (Base)
├── ProviderInitError      # 提供商初始化失败
├── ProviderApiError       # API调用失败(网络/超时/500)
├── QuotaExhaustedError    # 配额耗尽
├── ImageInvalidError      # 图片无效(格式损坏/超大)
├── NoFaceDetectedError    # 未检测到人脸
└── TargetNotFoundError    # 目标人物未注册
```

---

## 十二、数据库表概览

SQLite数据库文件: `data/crawl_photos.db`

| 表名 | 用途 |
|------|------|
| photos_record | 照片全生命周期记录 (photo_id唯一索引, SHA256去重) |
| task_queue | 持久化任务队列 (status/retry_count/priority/scheduled_at) |
| dead_letter_queue | 死信队列 (永久失败的任务,等待人工介入) |
| review_pool | 人工审核池 (confidence/status/reason/auto_approve_at) |
| audit_log | 操作审计日志 (actor/action/resource/detail/trace_id) |
| metrics_* | 指标历史数据 (counters/gauges/histograms) |

---

*本文档与 PRD_宝宝照片自动筛选工具.md 配合使用。PRD聚焦需求与功能规格，本文档聚焦技术实现与架构设计。*
