# 宝宝照片自动筛选工具 - 产品需求文档 (PRD)

| 文档版本 | V1.2 | 状态 | 修订 |
|---------|------|------|------|
| 创建日期 | 2026-04-16 | 作者 | 产品团队 |
| 最后更新 | 2026-04-16 | 审核人 | 待定 |

---

## 一、背景与痛点

### 1.1 业务背景
幼儿园老师每天放学后会在QQ群相册中上传当天所有小朋友的活动/学习照片，家长需要从大量照片中手动筛选出自己孩子的照片，费时费力且容易遗漏。

### 1.2 用户痛点
| 序号 | 痛点描述 | 影响程度 |
|-----|---------|---------|
| P1 | 每天需浏览几十至上百张照片逐一筛选，耗时5-15分钟 | 高 |
| P2 | 手动筛选容易遗漏重要瞬间（如孩子第一次上台表演） | 高 |
| P3 | 照片散落在群相册中，无法形成个人成长档案 | 中 |
| P4 | 手机空间有限，无法长期保存所有原始照片 | 中 |
| P5 | 老人/其他家庭成员想看孩子照片但不方便翻群相册 | 低 |

---

## 二、目标与范围

### 2.1 项目目标
- **核心目标**: 自动化完成"下载→识别→分类→归档→备份"全流程，将家长每日操作时间从5-15分钟降低至0分钟
- **延伸目标**: 构建宝宝成长影像档案系统

### 2.2 MVP功能范围 (V1.0)

| 功能模块 | 功能点 | 优先级 | 说明 |
|---------|-------|-------|------|
| QQ群相册同步 | 自动拉取群相册新增照片 | P0 | 核心功能 |
| 人脸识别引擎 | 基于参考图识别人脸并筛选 | P0 | 核心功能 |
| 本地归档管理 | 按年/月/日目录结构存储 | P0 | 核心功能 |
| 配置管理 | 目标人物、存储路径、QQ账号等配置 | P0 | 基础功能 |
| 日志监控 | 运行日志、异常告警、处理统计 | P1 | 运维保障 |
| 个人相册上传 | 筛选后自动上传到个人QQ相册 | P1 | 增值功能 |

### 2.3 非功能需求

| 维度 | 要求 |
|-----|------|
| **可靠性** | 7×24小时无人值守运行，异常自动恢复 |
| **准确性** | 人脸识别准确率 ≥95%，漏检率 ≤2% |
| **性能** | 单张照片识别耗时 <500ms，100张批次处理 <60s |
| **安全性** | QQ账号信息安全存储，本地数据不外传 |
| **易用性** | 配置一次即可长期运行，无需日常干预 |

---

## 三、用户角色与使用场景

### 3.1 用户画像
```
角色名称: 幼儿园家长(主要使用者)
年龄范围: 25-40岁
技术水平: 普通(会基本电脑操作)
核心诉求: 自动收集宝宝照片，不遗漏任何精彩瞬间
```

### 3.2 典型使用流程
```
[场景: 家长下班后的日常]

Before (无工具):
  打开QQ → 进入班级群 → 点击群相册 → 浏览今日相册
  → 逐张查看是否包含自己孩子 → 长按保存喜欢的照片
  → 整理到手机相册对应月份文件夹
  → 耗时: 5~15分钟

After (使用本工具):
  工具后台自动运行 → 下班后打开目标文件夹查看今日照片
  → 可选: 打开个人QQ相册分享给家人
  → 耗时: 0分钟(纯消费)
```

---

## 四、功能详述

### 4.1 QQ群相册数据采集

#### 4.1.1 数据源
- **来源**: QQ群相册(腾讯QQ)
- **触发方式**: 支持三种触发模式（详见4.1.5）
- **采集范围**: 指定QQ群的指定相册

#### 4.1.2 数据模型
```yaml
Photo:
  photo_id: string          # 照片唯一标识
  album_id: string          # 相册ID
  group_id: string          # 群号
  upload_time: datetime     # 上传时间
  uploader: string          # 上传者(老师昵称)
  url: string               # 照片原图URL
  thumbnail_url: string     # 缩略图URL
  file_size: int            # 文件大小(bytes)
  width: int                # 图片宽度
  height: int               # 图片高度
  local_path: string        # 本地存储路径(处理后)
  processed: bool           # 是否已处理
  contains_target: bool     # 是否包含目标人物
  confidence: float         # 识别置信度(0~1)
  created_at: datetime      # 记录创建时间
  updated_at: datetime      # 记录更新时间
```

#### 4.1.3 同步策略
| 策略项 | 方案 | 说明 |
|-------|------|------|
| 增量同步 | 基于upload_time去重 | 只处理新增照片 |
| 失败重试 | 指数退避,最多重试3次 | 网络抖动容错 |
| 断点续传 | 本地记录已处理photo_id | 重启后不重复处理 |
| 全局去重 | photo_id + file_hash双重校验 | 确保零重复（详见4.6节） |

#### 4.1.4 触发方式设计（三种模式并存）

```
┌──────────────────────────────────────────────────────────────┐
│                     触发模式架构                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ 模式A:事件触发 │   │ 模式B:定时触发 │   │ 模式C:手动触发  │  │
│  │ (实时性最好)  │   │ (可靠性最好)  │   │ (灵活性最强)   │  │
│  └──────┬───────┘   └──────┬───────┘   └───────┬────────┘  │
│         │                  │                    │           │
│         ▼                  ▼                    ▼           │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ QQ群消息监听  │   │ APScheduler  │   │ CLI命令 / API  │  │
│  │ Webhook回调   │   │ Cron调度器   │   │ HTTP接口调用    │  │
│  └──────┬───────┘   └──────┬───────┘   └───────┬────────┘  │
│         │                  │                    │           │
│         └──────────────────┼────────────────────┘           │
│                            ▼                                │
│                 ┌────────────────────┐                      │
│                 │  统一任务队列       │                      │
│                 │  (去重 + 幂等)      │                      │
│                 └────────┬───────────┘                      │
│                          ▼                                  │
│                 ┌────────────────────┐                      │
│                 │  执行采集+识别流程   │                      │
│                 └────────────────────┘                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**模式A: 事件触发（老师上传时自动触发）**
```yaml
原理: 监听QQ群消息,检测到"上传了X张照片到相册"类系统通知后立即触发
实现方案:
  方案A1 (推荐): 通过QQ机器人协议(go-cqhttp/Lagrange.Core)监听群消息,
                匹配相册上传通知正则 → 即时触发任务
  方案A2: 浏览器插件监听相册页面的DOM变化 → 调用本地HTTP API
  方案A3: 定时轮询间隔缩短至5分钟(伪实时)

优势:
  - 实时性最高,老师刚上传几分钟内即可完成筛选
  - 家长可第一时间收到新照片通知

劣势:
  - 需要保持QQ机器人在线/浏览器运行
  - 依赖第三方协议,稳定性不如定时触发

配置项:
  event_trigger:
    enabled: true                   # 是否启用事件触发
    listener_type: "bot"            # bot(机器人) / plugin(浏览器插件) / polling_short(高频轮询)
    poll_interval_minutes: 5        # 高频轮询间隔(仅polling_short模式)
    debounce_seconds: 60            # 防抖:同一批次上传等待60秒后再触发(避免多次触发)
```

**模式B: 定时触发（固定时间触发）**
```yaml
原理: 使用Cron表达式定义固定时间点执行
适用场景: 老师通常在放学后固定时间段(16:00~18:00)上传

推荐时间表:
  - 工作日: 每30分钟一次 (17:00 ~ 21:00 高频段)
  - 周末: 每2小时一次 (低频)
  - 自定义: 用户可配置任意Cron表达式

配置项:
  scheduler:
    cron_expression: "0 */30 17-21 * * 1-5"  # 工作日17-21点每30分钟
    startup_scan: true                           # 启动时全量扫描一次
    scan_days_back: 7                            # 启动回溯天数
```

**模式C: 手动触发（用户主动执行）**
```yaml
支持方式:
  1. 命令行触发:
     $ python main.py --run                    # 执行一次完整流程
     $ python main.py --run --days 3           # 回溯最近3天
     $ python main.py --run --date 2026-04-15  # 指定日期

  2. 本地Web API触发 (为小程序/Web界面预留):
     POST /api/v1/tasks/trigger
     {
       "trigger_type": "manual",
       "triggered_by": "user_web",
       "options": { "scan_days_back": 1 }
     }

  3. 系统托盘图标右键菜单 (GUI版本):
     [立即执行] [执行最近7天] [查看状态]

使用场景:
  - 刚配置完想立即测试效果
  - 怀疑有遗漏想重新扫描
  - 更换了参考照片后重新识别
```

### 4.2 人脸识别引擎（可插拔架构）

> **核心设计原则**: 人脸识别模块采用**策略模式(Strategy Pattern) + 插件化**架构，
> 所有识别提供商实现统一接口，通过配置文件一行即可切换，零代码改动。

#### 4.2.1 可插拔架构设计

```
┌───────────────────────────────────────────────────────────────┐
│                    人脸识别可插拔架构                           │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│                      调用方 (业务层)                           │
│                    ┌──────────────────┐                       │
│                    │ FaceRecognizer   │  ← 统一入口,不关心实现 │
│                    │  (Facade门面)     │                       │
│                    └────────┬─────────┘                       │
│                             │ 仅依赖抽象接口                   │
│                             ▼                                 │
│                    ┌──────────────────┐                       │
│                    │ IFaceRecognizer  │  ← 抽象基类/接口      │
│                    │  (ABC/Protocol)  │                       │
│                    └────────┬─────────┘                       │
│                             │                                 │
│         ┌───────────────────┼───────────────────┐            │
│         ▼                   ▼                   ▼            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ TencentCloud │    │    Baidu    │    │ InsightFace │     │
│  │  Provider    │    │  Provider   │    │  Provider   │     │
│  │ (云端API)    │    │ (云端API)   │    │ (本地模型)  │     │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘     │
│         │                   │                   │             │
│  ┌──────▼───────┐    ┌──────▼───────┐    ┌──────▼───────┐   │
│  │腾讯云AI服务   │    │ 百度AI服务   │    │ 本地ONNX/TFLite│  │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│                                                               │
│  切换方式: config.yaml 中修改 provider: "xxx" 即可             │
│  扩展方式: 新建文件,实现接口,注册到工厂,改配置                  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

#### 4.2.2 统一接口定义

```python
"""
人脸识别引擎 - 统一抽象接口
所有提供商必须实现此接口，保证调用方代码完全解耦
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path


class ProviderType(Enum):
    """支持的识别提供商类型"""
    TENCENT_CLOUD = "tencent_cloud"
    BAIDU = "baidu"
    FACE_PLUS = "face_plus"
    INSIGHT_FACE_LOCAL = "insight_face_local"
    ALIYUN = "aliyun"
    # 未来可扩展...
    CUSTOM = "custom"  # 用户自实现


@dataclass
class BoundingBox:
    """人脸边界框"""
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y,
                "width": self.width, "height": self.height}


@dataclass
class FaceDetection:
    """单次人脸检测结果"""
    face_id: str                          # 检测到的人脸唯一标识
    bounding_box: BoundingBox             # 边界框坐标
    confidence: float                     # 检测置信度 (0~1)
    face_image_path: Optional[str] = None # 裁剪出的人脸图片路径(可选)


@dataclass
class RecognitionResult:
    """单张照片的完整识别结果"""
    source_photo_path: str                # 原始照片路径
    total_faces_detected: int = 0         # 检测到的总人脸数
    target_matches: List[Dict] = field(default_factory=list)
    # 每个匹配项: {
    #   "target_name": "宝贝女儿",
    #   "confidence": 0.96,
    #   "face_box": BoundingBox,
    #   "face_image_path": "/tmp/face_crop.jpg"
    # }
    contains_target: bool = False         # 是否包含任意目标人物
    best_confidence: float = 0.0          # 最高匹配置信度
    all_face_detections: List[FaceDetection] = field(default_factory=list)
    provider_name: str = ""               # 实际使用的提供商名称
    processing_time_ms: float = 0.0       # 处理耗时(毫秒)
    raw_response: Optional[Dict[str, Any]] = None  # 原始响应(调试用)


@dataclass
class TargetConfig:
    """目标人物配置"""
    name: str                              # 人物名称标识
    reference_photo_paths: List[Path]      # 参考照片路径列表
    min_confidence: float = 0.80           # 最低匹配阈值
    enabled: bool = True                   # 是否启用
    feature_vector: Optional[bytes] = None # 缓存的特征向量(由提供商填充)


@dataclass
class ProviderInfo:
    """提供商能力描述信息"""
    provider_type: ProviderType           # 提供商标识
    display_name: str                     # 显示名称
    version: str                          # 版本号
    is_local: bool                        # 是否本地运行(无需网络)
    max_faces_per_image: int              # 单图最大检测人脸数
    supported_image_formats: List[str]    # 支持的图片格式
    requires_api_key: bool                # 是否需要API密钥
    has_batch_support: bool               # 是否支持批量处理
    estimated_cost_per_call: float        # 预估单次调用成本(元), 0=免费
    description: str                      # 提供商简介


class IFaceRecognizer(ABC):
    """
    人脸识别引擎 - 抽象基类(接口协议)

    所有识别提供商必须继承此类并实现所有abstractmethod。
    调用方仅依赖此接口,完全不感知底层实现细节。

    设计原则:
    - 单一职责: 只负责人脸相关操作
    - 开闭原则: 新增提供商只需新增子类,不改现有代码
    - 依赖倒置: 上层依赖抽象,不依赖具体实现
    - 接口隔离: 接口方法精简,每个方法单一功能
    """

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """返回此实现的提供商类型标识"""
        pass

    @property
    @abstractmethod
    def provider_info(self) -> ProviderInfo:
        """返回提供商的能力描述信息"""
        pass

    @abstractmethod
    async def initialize(self, targets: List[TargetConfig]) -> bool:
        """
        初始化识别引擎

        Args:
            targets: 目标人物配置列表,用于预加载特征库

        Returns:
            初始化是否成功

        Raises:
            ProviderInitError: 初始化失败时的异常
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查,检测服务可用性

        Returns:
            {
                "healthy": bool,
                "latency_ms": float,
                "quota_remaining": Optional[int],  # API剩余配额(如有)
                "message": str
            }
        """
        pass

    @abstractmethod
    async def detect_faces(
        self,
        image_path: str,
        max_faces: int = 10
    ) -> List[FaceDetection]:
        """
        检测图片中的人脸(不含识别/比对)

        Args:
            image_path: 图片文件路径(本地绝对路径或URL)
            max_faces: 最大检测人脸数量

        Returns:
            检测到的人脸列表(按置信度降序)

        Raises:
            ImageTooLargeError: 图片超过大小限制
            NoFaceDetectedError: 未检测到人脸(可不抛出,返回空列表)
            ProviderApiError: API调用失败
        """
        pass

    @abstractmethod
    async def recognize(
        self,
        image_path: str,
        target_names: Optional[List[str]] = None
    ) -> RecognitionResult:
        """
        核心方法: 识别图中是否包含目标人物(检测+特征提取+1:N搜索,一站式调用)

        这是对外暴露的主要方法,内部会依次执行:
        1. detect_faces() - 人脸检测
        2. extract_features() - 特征提取
        3. search_targets() - 与目标库比对

        Args:
            image_path: 待识别的图片路径
            target_names: 指定要匹配的目标人物名列表,
                         为None则匹配所有已注册目标

        Returns:
            RecognitionResult: 完整的识别结果

        Raises:
            ProviderApiError: API调用异常
            ImageInvalidError: 图片格式不支持或损坏
        """
        pass

    @abstractmethod
    async def add_reference_photos(
        self,
        target_name: str,
        photo_paths: List[str]
    ) -> bool:
        """
        为指定目标人物添加/更新参考照片

        典型使用场景:
        - 初始导入宝宝参考照
        - 定期更新参考照(孩子长相变化)
        - 发现漏检后补充新角度照片

        Args:
            target_name: 目标人物名称(需与TargetConfig.name一致)
            photo_paths: 参考照片文件路径列表

        Returns:
            是否成功添加

        Raises:
            TargetNotFoundError: 目标人物未注册
            InvalidPhotoError: 照片不符合要求(模糊/多人/无人脸等)
        """
        pass

    @abstractmethod
    async def remove_target(self, target_name: str) -> bool:
        """
        移除一个目标人物及其所有特征数据

        Args:
            target_name: 要移除的目标人物名称

        Returns:
            是否成功移除
        """
        pass

    @abstractmethod
    async def list_targets(self) -> List[Dict[str, Any]]:
        """
        列举当前已注册的所有目标人物及其状态

        Returns:
            [
                {
                    "name": "宝贝女儿",
                    "reference_count": 15,
                    "feature_vector_cached": True,
                    "last_updated": "2026-04-16T10:00:00"
                },
                ...
            ]
        """
        pass

    @abstractmethod
    async def batch_recognize(
        self,
        image_paths: List[str],
        target_names: Optional[List[str]] = None,
        concurrency: int = 5
    ) -> List[RecognitionResult]:
        """
        批量识别(可选优化接口)

        对于支持批量API的提供商(如腾讯云BatchDetectFace),
        可以在此方法中做并发或批处理优化。
        默认基类实现可以是简单的asyncio.gather逐张调用recognize()。

        Args:
            image_paths: 待识别的图片路径列表
            target_names: 指定匹配的目标
            concurrency: 并发数控制

        Returns:
            识别结果列表(与输入顺序一致)
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        清理资源,在程序退出时调用

        释放连接池、缓存、临时文件等
        """
        pass


# ========== 异常体系 ==========

class FaceRecognizerError(Exception):
    """人脸识别引擎基础异常"""
    pass

class ProviderInitError(FaceRecognizerError):
    """提供商初始化失败"""
    pass

class ProviderApiError(FaceRecognizerError):
    """提供商API调用失败"""
    def __init__(self, message: str, status_code: int = 0,
                 retryable: bool = True):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable  # 是否可重试

class QuotaExhaustedError(ProviderApiError):
    """API配额耗尽"""
    def __init__(self, message: str, reset_time: Optional[str] = None):
        super().__init__(message, retryable=False)
        self.reset_time = reset_time

class ImageInvalidError(FaceRecognizerError):
    """图片无效(格式错误/损坏/过大等)"""
    pass

class NoFaceDetectedError(FaceRecognizerError):
    """未检测到人脸"""
    pass

class TargetNotFoundError(FaceRecognizerError):
    """目标人物未找到"""
    pass
```

```

#### 4.2.3 插件注册与工厂机制

```python
"""
插件注册器 + 工厂模式
实现: 零配置自动发现 / 手动注册 / 一行切换提供商
"""

import importlib
from typing import Dict, Type, Optional


class FaceRecognizerRegistry:
    """
    人脸识别插件注册表 (单例)

    职责:
    - 维护 所有可用提供商的注册信息
    - 根据配置创建对应实例(工厂)
    - 提供查询/列举能力

    使用方式:
        registry = FaceRecognizerRegistry.get_instance()
        recognizer = registry.create("tencent_cloud", config)
    """

    _instance: Optional["FaceRecognizerRegistry"] = None
    _providers: Dict[ProviderType, Type[IFaceRecognizer]] = {}

    def __init__(self):
        # 内置提供商自动注册
        self._register_builtin_providers()

    @classmethod
    def get_instance(cls) -> "FaceRecognizerRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        provider_type: ProviderType,
        provider_class: Type[IFaceRecognizer]
    ) -> None:
        """注册一个提供商实现类"""
        if not issubclass(provider_class, IFaceRecognizer):
            raise TypeError(
                f"{provider_class.__name__} must implement IFaceRecognizer"
            )
        self._providers[provider_type] = provider_class

    def unregister(self, provider_type: ProviderType) -> None:
        """移除一个提供商"""
        self._providers.pop(provider_type, None)

    def create(
        self,
        provider_type: ProviderType,
        **config_kwargs
    ) -> IFaceRecognizer:
        """
        工厂方法: 根据类型创建实例

        Args:
            provider_type: 目标提供商类型
            **config_kwargs: 该提供商所需的配置参数

        Returns:
            初始化好的识别引擎实例

        Raises:
            ProviderNotFoundError: 未注册的提供商类型
            ProviderInitError: 初始化失败
        """
        if provider_type not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(
                f"Unknown provider: {provider_type}. "
                f"Available: {available}"
            )

        provider_class = self._providers[provider_type]
        instance = provider_class(**config_kwargs)
        return instance

    def list_available(self) -> Dict[ProviderType, ProviderInfo]:
        """列举所有已注册的提供商及其能力描述"""
        result = {}
        for ptype, pclass in self._providers.items():
            # 实例化临时对象获取info(不初始化连接)
            try:
                info = pclass.provider_info  # 类属性或实例属性
                result[ptype] = info
            except Exception:
                result[ptype] = ProviderInfo(
                    provider_type=ptype,
                    display_name=pclass.__name__,
                    version="unknown",
                    is_local=False,
                    max_faces_per_image=0,
                    supported_image_formats=[],
                    requires_api_key=True,
                    has_batch_support=False,
                    estimated_cost_per_call=0,
                    description="信息获取失败"
                )
        return result

    def _register_builtin_providers(self) -> None:
        """自动注册内置提供商"""
        # 延迟导入,避免未安装依赖时报错
        builtin_mappings = {
            ProviderType.TENCENT_CLOUD:
                "app.face_recognition.providers.tencent_cloud"
                ".TencentCloudProvider",
            ProviderType.BAIDU:
                "app.face_recognition.providers.baidu.BaiduProvider",
            ProviderType.INSIGHT_FACE_LOCAL:
                "app.face_recognition.providers.insight_face"
                ".InsightFaceLocalProvider",
            ProviderType.FACE_PLUS:
                "app.face_recognition.providers.face_plus.FacePlusProvider",
        }

        for ptype, module_path in builtin_mappings.items():
            try:
                module_path_parts = module_path.rsplit(".", 1)
                module = importlib.import_module(module_path_parts[0])
                cls = getattr(module, module_path_parts[1])
                self.register(ptype, cls)
            except ImportError:
                # 对应SDK未安装时跳过,不阻塞启动
                pass


# ========== 门面类(Facade) ==========

class FaceRecognizerFacade:
    """
    人脸识别门面类 - 业务层的唯一交互入口

    职责:
    - 封装提供商选择逻辑(读配置,调工厂创建)
    - 统一异常处理和日志
    - 提供降级/熔断机制(可选)
    - 对调用方完全屏蔽底层差异

    设计模式: Facade + Strategy 的组合
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._recognizer: Optional[IFaceRecognizer] = None
        self._registry = FaceRecognizerRegistry.get_instance()
        self._initialize_from_config()

    def _initialize_from_config(self) -> None:
        """
        从配置文件读取并初始化识别引擎

        配置示例(config.yaml):
            face_recognition:
              provider: "tencent_cloud"       # <-- 只需改这里即可切换!
              tencent_cloud:
                secret_id: "${SECRET_ID}"
                secret_key: "${SECRET_KEY}"
                region: "ap-guangzhou"

        切换到百度只需改为:
            provider: "baidu"
            baidu:
              api_key: "xxx"
              secret_key: "yyy"
        """
        provider_name = self._config.get("provider", "tencent_cloud")

        # 字符串转枚举
        try:
            provider_type = ProviderType(provider_name)
        except ValueError:
            raise ValueError(
                f"Unsupported provider: {provider_name}. "
                f"Available: {[p.value for p in ProviderType]}"
            )

        # 获取该提供商的专属配置
        provider_config = self._config.get(provider_name, {})

        # 环境变量替换 (${VAR} 形式)
        provider_config = self._resolve_env_vars(provider_config)

        # 通过工厂创建实例
        self._recognizer = self._registry.create(
            provider_type, **provider_config
        )

    async def recognize(self, image_path: str, **kwargs) -> RecognitionResult:
        """委托给实际提供商执行识别"""
        if self._recognizer is None:
            raise FaceRecognizerError("Recognizer not initialized")
        return await self._recognizer.recognize(image_path, **kwargs)

    async def batch_recognize(self, paths: List[str], **kwargs):
        """批量识别"""
        if self._recognizer is None:
            raise FaceRecognizerError("Recognizer not initialized")
        return await self._recognizer.batch_recognize(paths, **kwargs)

    @property
    def current_provider_info(self) -> ProviderInfo:
        """当前使用的提供商信息"""
        if self._recognizer:
            return self._recognizer.provider_info
        return ProviderInfo(...)  # 空信息

    async def switch_provider(self, new_provider: str,
                              new_config: Dict) -> bool:
        """运行时动态切换提供商(热切换)"""
        # 清理旧实例
        if self._recognizer:
            await self._recognizer.cleanup()

        # 更新配置并重建
        self._config["provider"] = new_provider
        self._config[new_provider] = new_config
        self._initialize_from_config()
        return True
```

#### 4.2.4 内置提供商实现规格

每个提供商需要实现的文件结构:

```
app/
  face_recognition/                  # 人脸识别模块根包
    __init__.py                      # 导出 Facade 和 接口
    interfaces.py                    # IFaceRecognizer 抽象基类 (如上定义)
    models.py                        # 数据模型 (RecognitionResult 等)
    exceptions.py                    # 自定义异常体系
    registry.py                      # 注册表 + 工厂 (如上定义)
    facade.py                        # 门面类 (如上定义)
    |
    providers/                       # 各提供商实现目录
      __init__.py
      base.py                        # 抽象基类(可选,提供通用辅助方法)
      |
      tencent_cloud/                 # 腾讯云实现
      ├── __init__.py
      ├── provider.py                # TencentCloudProvider 类
      ├── client.py                  # API客户端封装
      └── utils.py                   # 图片编码/签名等工具函数
      |
      baidu/                         # 百度AI实现
      ├── __init__.py
      ├── provider.py
      └── ...
      |
      insight_face/                  # InsightFace本地模型实现
      ├── __init__.py
      ├── provider.py
      ├── model_loader.py            # ONNX模型加载器
      └── ...
      |
      face_plus/                     # Face++实现
      ├── __init__.py
      └── ...
```

##### Provider A: TencentCloudProvider (默认)

```yaml
provider_type: tencent_cloud
display_name: "腾讯云人脸识别"
version: "3.0"
is_local: false
requires_api_key: true
has_batch_support: true          # 支持批量检测API
estimated_cost_per_call: 0.001   # 约0.001元/次(付费版)
free_quota: 1000                 # 免费额度: 1000次/月
max_faces_per_image: 10
supported_image_formats: [jpg, jpeg, png, bmp]

API端点:
  - DetectFace (人脸检测): https://iai.tencentcloudapi.com/
  - SearchFaces (人脸搜索1:N): 同上
  - CreateFace (创建人员库): 同上

关键特性:
  ✅ 准确率最高(99%+),中文场景优化最好
  ✅ 支持人员库(GroupId)持久化存储特征向量
  ✅ 支持批量API(BatchDetectFace)降低延迟
  ❌ 需要网络连接
  ⚠️  免费额度有限(1000次/月)

实现要点:
  1. 初始化时调用 CreateGroup 创建人员库(如不存在)
  2. add_reference_photos 时调用 CreatePerson 上传参考照到人员库
  3. recognize 时调用 DetectFace + SearchFaces 两步完成
  4. 特征向量由云端维护,无需本地缓存
```

##### Provider B: BaiduProvider

```yaml
provider_type: baidu
display_name: "百度AI人脸识别"
version: "3.0"
is_local: false
requires_api_key: true
has_batch_support: true
estimated_cost_per_call: 0.0007   # 约0.0007元/次
free_quota: 10000                # QPS限制内免费(认证用户)
max_faces_per_image: 10
supported_image_formats: [jpg, jpeg, png, bmp]

API端点:
  - 人脸检测: https://aip.baidubce.com/rest/2.0/face/v3/detect
  - 人脸搜索: https://aip.baidubce.com/rest/2.0/face/v3/search
  - 人脸库管理: .../face/v3/faceset/user/add

关键特性:
  ✅ 免费额度最大(QPS限制内基本免费)
  ✅ 文档清晰,SDK成熟
  ⚠️  准确度略低于腾讯云(约97%)
  ❌ 需要网络连接

实现要点:
  1. 使用 FaceSet 管理人脸库
  2. 支持活体检测选项(liveness_control)
  3. 返回的quality_score可用于过滤低质量图片
```

##### Provider C: InsightFaceLocalProvider (离线方案)

```yaml
provider_type: insight_face_local
display_name: "InsightFace 本地识别"
version: "1.0" (基于insightface 0.7+)
is_local: true                    # 无需网络!
requires_api_key: false           # 无需API Key!
has_batch_support: true           # GPU可并行
estimated_cost_per_call: 0.0      # 完全免费
max_faces_per_image: 20
supported_image_formats: [jpg, jpeg, png, bmp, webp]

模型依赖:
  - detection model: buffalo_l (推荐) / SCRFD
  - recognition model: w600k_r50 (onnx格式)
  - 运行时: onnxruntime (CPU/GPU均可)

关键特性:
  ✅ 完全离线运行,无网络依赖
  ✅ 无限免费调用,无配额限制
  ✅ 数据不出本机,隐私性最好
  ✅ 延迟低(本地推理 <200ms/张,有GPU更快)
  ⚠️  CPU模式下准确率略低于云端(约95% vs 99%)
  ⚠️  首次需下载模型文件(~200MB)
  ⚠️  特征向量需自己管理存储(SQLite blob)

硬件要求:
  - 最低: 4核CPU + 8GB内存(CPU推理,~500ms/张)
  - 推荐: NVIDIA GTX 1060以上(GPU推理,~50ms/张)

实现要点:
  1. init时加载ONNX模型到内存/显存
  2. 参考照提取特征后存入SQLite(blob字段)
  3. recognize时用余弦相似度(cosine similarity)匹配
  4. 支持faiss加速向量检索(大量参考照时)
```

##### Provider D: FacePlusProvider

```yaml
provider_type: face_plus
display_name: "Face++ 人脸识别"
version: "3.0"
is_local: false
requires_api_key: true
has_batch_support: false
estimated_cost_per_call: 0.01      # 较贵
free_quota: 0                     # 无永久免费额度(仅试用)
max_faces_per_image: 10
supported_image_formats: [jpg, jpeg, png]

关键特性:
  ✅ API设计友好,文档完善
  ✅ 支持人脸关键点检测(83/106点)
  ❌ 商用收费较高
  ❌ 无长期免费额度

适用场景: 作为备选方案,或在其他三家都不满足特殊需求时使用
```

#### 4.2.5 切换提供商的操作指南

```bash
# 场景1: 从腾讯云切换到百度 (改1行配置即可)
# -------------------------------------------------
# 编辑 config.yaml:

# 原来:
face_recognition:
  provider: "tencent_cloud"
  tencent_cloud:
    secret_id: "xxx"
    secret_key: "yyy"
    region: "ap-guangzhou"

# 改为:
face_recognition:
  provider: "baidu"                          # <-- 只改这一行!
  baidu:                                     # <-- 新增百度配置段
    api_key: "your_baidu_api_key"
    secret_key: "your_baidu_secret_key"

# 重启服务即可,业务代码零改动!


# 场景2: 从云端切到离线 (断网环境)
# -------------------------------------------------
face_recognition:
  provider: "insight_face_local"             # <-- 切换到离线模式
  insight_face_local:
    model_name: "buffalo_l"                 # 模型选择
    device: "cpu"                            # 或 "cuda:0" 如果有GPU
    model_cache_dir: "data/models"           # 模型缓存目录
    confidence_threshold: 0.80               # 匹配阈值

# 注意: 首次使用需下载模型文件(~200MB),程序会自动处理


# 场景3: 开发自定义提供商
# -------------------------------------------------
# 步骤1: 在 app/face_recognition/providers/my_custom/ 下新建 provider.py

from app.face_recognition.interfaces import (
    IFaceRecognizer, ProviderType, ProviderInfo,
    RecognitionResult, TargetConfig, FaceDetection
)

# 注册自定义类型(在枚举中添加)
class ProviderType(Enum):
    TENCENT_CLOUD = "tencent_cloud"
    BAIDU = "baidu"
    # ... 已有的 ...
    MY_CUSTOM = "my_custom"                  # <-- 新增

# 步骤2: 实现 IFaceRecognizer 接口
class MyCustomProvider(IFaceRecognizer):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.MY_CUSTOM

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_type=ProviderType.MY_CUSTOM,
            display_name="我的自定义识别",
            version="1.0",
            is_local=True,
            # ... 其他属性
        )

    async def initialize(self, targets): ...
    async def recognize(self, image_path, target_names=None): ...
    # ... 实现所有抽象方法 ...

# 步骤3: 在 registry 中注册
# app/face_recognition/providers/__init__.py 中添加:
from .my_custom.provider import MyCustomProvider

# 步骤4: 配置中使用
face_recognition:
  provider: "my_custom"                     # <-- 直接用!
```

#### 4.2.6 识别流程
```
┌──────────────────────────────────────────────────────┐
│                    识别流程                            │
├──────────────────────────────────────────────────────┤
│                                                      │
│   输入照片                                           │
│       │                                              │
│       ▼                                              │
│  ┌─────────┐    否    ┌──────────────┐              │
│  │检测人脸 │────────▶│ 标记为无关照  │              │
│  └────┬────┘          └──────────────┘              │
│       │是                                             │
│       ▼                                              │
│  ┌─────────┐                                        │
│  │提取特征  │                                        │
│  │ 向量     │                                        │
│  └────┬────┘                                        │
│       │                                              │
│       ▼                                              │
│  ┌─────────────────┐                                │
│  │ 与目标人物库对比  │◀──── 目标人物特征库             │
│  │ (1:N人脸搜索)    │     (预录入的宝宝照片)          │
│  └────┬────────────┘                                │
│       │                                              │
│       ├─▶ 相似度 ≥ 阈值(如0.8) → ✅ 包含目标人物     │
│       │                                              │
│       └─▶ 相似度 < 阈值      → ❌ 不包含目标人物      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

#### 4.2.3 目标人物库管理
- 支持导入多张参考照片(建议10-20张不同角度/表情)
- 特征向量定期更新(孩子长相变化快)
- 支持多目标人物同时筛选(如同时关注多个孩子)

### 4.3 本地归档管理

#### 4.3.1 目录结构设计
```
{根目录}/
├── 2026/
│   ├── 01_January/
│   │   ├── 2026-01-15/
│   │   │   ├── IMG_001.jpg
│   │   │   ├── IMG_002.jpg
│   │   │   └── metadata.json          # 当日元数据
│   │   └── ...
│   ├── 02_February/
│   └── ...
├── 2027/
│   └── ...
├── config.yaml                       # 全局配置文件
├── logs/                             # 运行日志
│   ├── app_2026-04-16.log
│   └── error_2026-04-16.log
└── data/                             # 运行时数据(数据库)
    ├── crawl_photos.db               # SQLite数据库
    └── cache/                        # 缓存(已处理记录等)
```

#### 4.3.2 文件命名规则
```
格式: {YYYYMMDD}_{序号}_{来源标识}.{扩展名}
示例: 20260416_0001_qqgroup.jpg
      20260416_0002_qqgroup.jpg

说明:
  - YYYYMMDD: 照片原始上传日期
  - 序号: 当天第几张(4位数字,前补零)
  - 来源标识: qqgroup(群相册) / personal(个人相册)
```

#### 4.3.3 元数据文件(metadata.json)
```json
{
  "date": "2026-04-16",
  "total_photos": 45,
  "target_photos": 12,
  "source": "qq_group_album",
  "group_name": "阳光小班",
  "uploader": "李老师",
  "process_time": "2026-04-16T18:35:22",
  "photos": [
    {
      "filename": "20260416_0001_qqgroup.jpg",
      "original_id": "xxx",
      "confidence": 0.96,
      "face_count": 1,
      "tags": ["户外活动", "集体游戏"]
    }
  ]
}
```

### 4.4 个人相册上传(可选)

#### 4.4.1 上传策略
| 策略项 | 方案 | 说明 |
|-------|------|------|
| 上传时机 | 筛选完成后立即上传 | 保证时效性 |
| 相册命名 | `{年份}年{月份}宝宝照片` | 如"2026年4月宝宝照片" |
| 相册自动创建 | 按月自动创建新相册 | 不存在则创建 |
| 去重机制 | 基于照片hash去重 | 避免重复上传 |
| 失败处理 | 加入重试队列,下次执行 | 网络问题容错 |

#### 4.4.2 权限设置
- 默认仅自己可见
- 可选开放给指定家庭成员(QQ好友)

### 4.5 配置管理

#### 4.5.1 配置文件结构(config.yaml)
```yaml
# ==================== QQ群相册配置 ====================
qq:
  # 群相册配置
  group:
    group_id: "123456789"           # 班级QQ群号
    album_id: "album_xxx"           # 目标相册ID(留空则扫描全部)
    cookies_file: "data/qq_cookies.txt"  # QQ登录Cookie文件
  
  # 个人相册配置(可选,用于上传)
  personal:
    enabled: false                   # 是否启用自动上传
    album_prefix: "{year}年{month}月宝宝照片"
    visibility: "self_only"          # self_only / family

# ==================== 人脸识别配置（可插拔） ====================
face_recognition:
  # ====== 核心切换开关: 只需改这一行即可更换提供商! ======
  provider: "tencent_cloud"
  # 可选值:
  #   "tencent_cloud"     - 腾讯云人脸识别 (推荐,准确率99%+,1000次/月免费)
  #   "baidu"             - 百度AI人脸识别 (免费额度大,QPS限制内免费)
  #   "insight_face_local"- InsightFace本地模型 (完全离线,无网络依赖)
  #   "face_plus"         - Face++ (商用收费较高)
  #   "custom"            - 自定义提供商(需自行实现IFaceRecognizer接口)

  # ====== 提供商A: 腾讯云 ======
  tencent_cloud:
    secret_id: "${TENCENT_SECRET_ID}"     # 从环境变量读取(安全!)
    secret_key: "${TENCENT_SECRET_KEY}"
    region: "ap-guangzhou"
    group_id: "baby_photos_group"        # 人员库ID(自动创建)

  # ====== 提供商B: 百度AI ======
  baidu:
    app_id: "${BAIDU_APP_ID}"
    api_key: "${BAIDU_API_KEY}"
    secret_key: "${BAIDU_SECRET_KEY}"
    group_id: "baby_photos_group"

  # ====== 提供商C: InsightFace 本地模型(离线) ======
  insight_face_local:
    model_name: "buffalo_l"              # 模型选择: buffalo_l(推荐) / buffalo_s(轻量)
    device: "cpu"                        # 推理设备: cpu / cuda:0 / mps(Apple Silicon)
    model_cache_dir: "data/models"       # ONNX模型文件缓存目录(~200MB)
    confidence_threshold: 0.80           # 余弦相似度匹配阈值
    use_faiss: false                     # 是否启用faiss加速(大量参考照时推荐)

  # ====== 目标人物配置(所有提供商共用) ======
  targets:
    - name: "宝贝女儿"
      reference_photos_dir: "config/reference_photos/daughter/"
      min_confidence: 0.80               # 该人物的最低置信度阈值
      enabled: true

    # 可添加更多目标人物(多孩家庭)
    # - name: "儿子"
    #   reference_photos_dir: "config/reference_photos/son/"
    #   min_confidence: 0.80
    #   enabled: true

# ==================== 存储配置 ====================
storage:
  root_directory: "D:/BabyPhotos"    # 照片存储根目录
  directory_format: "{root}/{year}/{month_num}_{month_name}/{date}"
  filename_format: "{date}_{seq:04d}_qqgroup.{ext}"
  retain_original_filename: true      # 是否保留原文件名作为备注

# ==================== 调度配置 ====================
scheduler:
  cron_expression: "0 */30 * * * *"  # 每30分钟执行一次
  startup_scan: true                  # 启动时全量扫描一次
  scan_days_back: 7                   # 启动回溯天数

# ==================== 日志配置 ====================
logging:
  level: "INFO"                      # DEBUG / INFO / WARN / ERROR
  directory: "logs"
  max_file_size_mb: 50               # 单个日志文件最大大小
  retention_days: 90                 # 日志保留天数

# ==================== 通知配置(可选) ====================
notification:
  enabled: false
  type: "wechat"                     # wechat / email / dingtalk
  wechat_webhook: ""                 # 企业微信机器人Webhook
  notify_on_new_photo: true          # 发现新照片时通知
  notify_on_error: true              # 出错时通知
  daily_summary: true                # 每日汇总报告
  summary_time: "21:00"             # 每日报告发送时间
```

### 4.6 全局去重机制（核心保障）

#### 4.6.1 去重目标
**绝对保证**: 同一张照片不会重复下载到本地，也不会重复上传到QQ个人相册

#### 4.6.2 三层去重策略
```
第一层: 任务入队去重
  基于photo_id的内存集合(Set),同一photo_id不重复加入
  防止: 多种触发模式(A/B/C)同时触发导致同一照片被处理多次

第二层: 数据库持久化去重
  SQLite表 photos_record 记录每张照片的全生命周期状态
  查询前先查库,已存在的记录直接跳过
  防止: 程序重启后丢失内存状态导致重复处理

第三层: 文件级Hash校验
  对下载后的文件计算SHA256哈希值
  存储时比对hash,即使文件名不同也拒绝覆盖
  防止: photo_id变更但实际是同一张文件的情况
```

#### 4.6.3 数据库去重表设计
```sql
CREATE TABLE IF NOT EXISTS photos_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_photo_id TEXT NOT NULL UNIQUE,   -- 群相册照片ID(全局唯一)
    source_type     TEXT NOT NULL DEFAULT 'qq_group',
    file_hash       TEXT NOT NULL UNIQUE,   -- SHA256文件哈希
    original_url    TEXT,
    original_filename TEXT,
    file_size       INTEGER,
    upload_time     DATETIME,
    uploader        TEXT,

    -- 状态机: pending->downloaded->recognized->stored->uploaded->completed
    --        pending->skipped / pending->failed
    status          TEXT NOT NULL DEFAULT 'pending',

    contains_target BOOLEAN DEFAULT FALSE,
    target_names    TEXT,                   -- JSON数组
    confidence      REAL,
    face_count      INTEGER DEFAULT 0,

    local_path      TEXT,
    local_filename  TEXT,

    personal_album_id   TEXT,
    personal_photo_id   TEXT,              -- 个人相册照片ID(防重复上传)
    upload_status       TEXT DEFAULT 'pending',

    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_source UNIQUE (source_photo_id, source_type),
    CONSTRAINT uk_hash UNIQUE (file_hash)
);

CREATE INDEX idx_photos_status ON photos_record(status);
CREATE INDEX idx_photos_upload_time ON photos_record(upload_time);

-- 上传重试队列表
CREATE TABLE IF NOT EXISTS upload_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER NOT NULL REFERENCES photos_record(id),
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    next_retry_at   DATETIME,
    error_message   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 4.6.4 去重流程详解
```
采集阶段:
  获取新照片列表 -> 遍历 -> 查库(source_photo_id)
    存在且completed/skipped => 跳过
    存在且failed => 重试
    不存在 => 插入(pending),入队

下载阶段:
  下载到临时目录 -> 计算SHA256 -> 查库(file_hash)
    已存在 => 删临时文件,复用记录

存储阶段:
  检查目标目录文件是否存在 + size校验
    已存在但缺记录 => 补记录,不覆盖

上传阶段:
  查 personal_photo_id IS NOT NULL AND status='uploaded'
    已上传 => 跳过
  上传成功 => 记录ID,标记uploaded
```

#### 4.6.5 去重配置项
```yaml
deduplication:
  enable_memory_dedup: true         # 内存去重
  enable_db_dedup: true             # 数据库去重
  enable_file_hash_dedup: true      # Hash去重
  hash_algorithm: "sha256"          # md5 / sha1 / sha256
  consistency_check:
    enabled: true                   # 数据一致性自检
    schedule: "0 3 * * *"           # 凌晨3点
    auto_fix: false                 # 仅报告不自动修复
```

### 4.7 QQ小程序 / 微信小程序（Phase 5 后续补充）

> **定位**: 移动端浏览与管理入口，手机上随时随地查看宝宝精选照片。
>
> **开发优先级**: P2（V2.0规划），MVP阶段仅提供本地Web界面或命令行操作。

#### 4.7.1 产品形态选择

| 方案 | 平台 | 优势 | 劣势 | 推荐度 |
|------|------|------|------|--------|
| **微信小程序** | 微信 | 用户基数大,无需安装,分享方便 | 需备案域名+HTTPS | **首选** |
| QQ小程序 | QQ | QQ生态打通 | 用户量较小 | 备选 |
| H5 Web页面 | 浏览器 | 开发最快,跨平台 | 无原生体验 | MVP过渡 |

**策略: V1.x 用 H5/本地Web → V2.0 升级为微信小程序**

#### 4.7.2 功能范围（分阶段）
```
功能模块          MVP(V1.x)     V2.0(小程序)    V3.0(增强)
----------------------------------------------------------
照片瀑布流浏览    本地文件夹       实现           AI智能分类
日历视图(按日期)     无            实现           时间轴故事线
照片详情(大图)    图片查看器       实现           人物关系标注
统计概览仪表盘    CLI输出         实现           成长曲线图
手动触发筛选      CLI命令         实现           语音触发
配置管理          YAML编辑      基础设置页       完整设置中心
分享功能           无           生成海报         家庭共享相册
保存到手机        本地已有        实现           批量打包下载
消息通知推送      企业微信       订阅消息推送      实时推送
多家庭成员          无            无             多账号权限
```

#### 4.7.3 页面结构设计
```
底部TabBar: [首页] [日历] [我的]

首页 - 最新照片瀑布流:
  - 顶部卡片: 今日新增数 + 最后同步时间
  - 瀑布流列表 (懒加载/下拉刷新/上拉加载)
  - 卡片信息: 缩略图 + 日期 + 置信度徽章
  - 点击进入大图预览(左右滑动)

日历 - 按日期浏览:
  - 月历热力图(有照日期高亮+数量)
  - 点击日期 -> 当天照片列表
  - 左右滑动切月份

我的 - 个人中心:
  - 存储统计(总数/空间/月趋势)
  - 运行状态(同步时间/Cookie有效期)
  - 功能入口: 手动触发/设置/关于

二级页面:
  - 照片详情: 大图 + 人脸框 + 元信息 + 保存/删除/分享
  - 月度汇总: 统计柱状图 + 精选轮播
  - 设置页: 配置修改 + 参考照管理 + 通知偏好
```

#### 4.7.4 技术架构
```
[小程序/H5前端] --HTTPS--> [API服务 FastAPI] --> [主程序]
                                         |
                                   SQLite + 文件系统
```

#### 4.7.5 核心API接口（预留）
```yaml
GET  /api/v1/photos              # 照片列表(分页,多维度筛选)
GET  /api/v1/photos/{id}         # 照片详情(含人脸位置)
GET  /api/v1/photos/{id}/file    # 照片文件流(支持缩略图)
GET  /api/v1/photos/calendar/{year}/{month}  # 月度日历数据
POST /api/v1/tasks/trigger       # 手动触发筛选任务
GET  /api/v1/tasks/{task_id}     # 查询任务进度
GET  /api/v1/system/status       # 系统运行状态总览
GET  /api/v1/stats/summary       # 统计概览
```

---

## 五、技术架构

### 5.1 整体架构图
```
┌───────────────────────────────────────────────────────────────────────┐
│                           用户层                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ CLI命令行 │ │本地文件夹│ │Web浏览器  │ │企业微信   │ │微信小程序   │ │
│  │手动触发  │ │直接浏览  │ │H5管理界面 │ │通知推送   │ │(V2.0)     │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘ │
└───────┼────────────┼────────────┼────────────┼─────────────┼─────────┘
        │            │            │            │             │
┌───────▼────────────▼────────────▼────────────▼─────────────▼─────────┐
│                         接入层                                         │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    API 服务网关 (V1.x可选, V2.0核心)          │    │
│  │              FastAPI / Flask REST Server                     │    │
│  │  照片浏览API | 任务触发API | 统计API | 系统状态API           │    │
│  │  (V1.0: disabled; V2.0: enabled for mini-program support)   │    │
│  └──────────────────────────┬─────────────────────────────────┘    │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                          应用层                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    宝宝照片管家 (主程序)                       │   │
│  │                                                               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │   │
│  │  │调度引擎  │ │配置管理器 │ │日志服务  │ │ 通知服务       │  │   │
│  │  │(3种模式) │ │          │ │         │ │                │  │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬────────┘  │   │
│  │  ┌────┴────────────┴──────────┴──────────────┴─────┐        │   │
│  │  │                 编排层 (去重 + 幂等)            │        │   │
│  │  └────────────────────┬──────────────────────────┘        │   │
│  │  ┌──────────┐  ┌──────┴──────┐  ┌──────────────────┐      │   │
│  │  │相册采集器│  │人脸识别引擎  │  │  存储管理器      │      │   │
│  │  └────┬─────┘  └──────┬─────┘  └───────┬──────────┘      │   │
│  └───────┼───────────────┼─────────────────┼─────────────────┘   │
└──────────┼───────────────┼─────────────────┼─────────────────────┘
           │               │                 │
┌──────────▼───────┐ ┌─────▼────────┐ ┌──────▼────────────────┐     │
│   外部依赖层      │ │  AI服务层    │ │     存储层              │     │
│ ┌──────────────┐ │ │ ┌──────────┐ │ │ ┌──────────────────┐  │     │
│ │QQ群相册(Cookie)│ │ │腾讯云人脸  │ │ │  本地文件系统      │  │     │
│ ├──────────────┤ │ │识别API    │ │ │ D:/BabyPhotos/    │  │     │
│ │QQ空间(个人相册)│ │ └──────────┘ │ │ ├──────────────────┤  │     │
│ ├──────────────┤ │ │ ┌──────────┐ │ │ │ SQLite数据库     │  │     │
│ │QQ机器人(事件)  │ │ │本地特征   │ │ │ photos_record表  │  │     │
│ └──────────────┘ │ │ 向量缓存   │ │ │ upload_queue表   │  │     │
│                   │ │ └──────────┘ │ │ └──────────────────┘  │     │
└───────────────────┘ └─────────────┘ └─────────────────────────┘     │

触发方式一览:
  [A]事件触发: QQ机器人消息/Webhook -> 实时响应老师上传
  [B]定时触发: APScheduler Cron -> 固定时间自动执行
  [C]手动触发: CLI命令 / API调用 / Web按钮 -> 用户主动发起
```

### 5.2 技术选型

| 层面 | 技术选择 | 选择理由 |
|-----|---------|---------|
| **编程语言** | Python 3.10+ | 生态丰富,AI库支持最好 |
| **定时调度** | APScheduler | 轻量级,支持cron表达式,3种触发器(trigger) |
| **HTTP客户端** | httpx(异步) | 异步高性能,替代requests |
| **QQ协议** | go-cqhttp / Lagrange.Core 或 Cookie模拟 | 消息监听+相册数据获取 |
| **人脸识别** | 可插拔架构 (IFaceRecognizer + Registry + Facade) | 默认腾讯云;支持百度/InsightFace/Face++;一行配置切换 |
| **数据存储** | SQLite (通过sqlalchemy/aiosqlite) | 轻量零运维,单机够用 |
| **配置管理** | PyYAML | YAML格式,人类可读,支持环境变量引用 |
| **日志框架** | loguru | 简洁好用,自动轮转,性能好 |
| **通知推送** | requests + 企业微信Webhook | 免费,到达率高 |
| **API服务** | FastAPI (V2.0启用) | 自动文档,异步支持,类型检查 |
| **小程序前端** | 原生微信小程序 + TDesign组件库 (V2.0) | 官方推荐UI组件库 |
| **H5过渡方案** | Vue3 + Vite (V1.x) | 快速出原型,后续迁移到小程序 |
| **打包分发** | PyInstaller / Docker | exe独立包或容器化部署 |

### 5.3 数据流图
```
  QQ群相册                              宝宝照片管家                           本地磁盘
┌──────────────┐                   ┌──────────────────┐                   ┌──────────────┐
│              │  ①定时轮询新增照片 │                  │                   │              │
│  新增照片列表 │─────────────────▶│  相册采集器       │                   │              │
│              │                   │      │           │                   │              │
└──────────────┘                   │      ▼ ②下载图片  │                   │              │
                                   │  ┌───────┐        │                   │              │
                                   │  │临时缓冲│        │                   │              │
                                   │  └───┬───┘        │                   │              │
                                   │      │ ③人脸检测   │                   │              │
                                   │      ▼             │                   │              │
                                   │  ┌───────────┐     │                   │              │
                                   │  │人脸识别引擎 │     │                   │              │
                                   │  └─────┬─────┘     │                   │              │
                                   │        │ ④返回结果  │                   │              │
                   ┌───────┐      │  ┌─────▼─────┐     │                   │              │
                   │ 包含?  │◀─────┤  │ 结果判断   │     │                   │              │
                   └───┬───┘      │  └─────┬─────┘     │                   │              │
                  是   │   否      │        │           │                   │              │
                   ┌──▼───┐  ┌─────▼─────┐   │           │  ⑤按月归档       │  ┌───────────┐│
                   │ 保留  │  │ 丢弃标记  │   │           │─────────────────▶│ 月度文件夹  ││
                   └──┬───┘  └──────────┘   │           │                   │           ││
                      │                    │           │                   │           ││
                      │ ⑥可选:上传个人相册 │           │                   │           ││
                      ▼                    │           │                   │           ││
                   ┌──────────┐            │           │                   │           ││
                   │QQ空间API │◀───────────┤───────────┤                   │           ││
                   └──────────┘  ⑦上传成功  │           │                   │           ││
                                       │           │  ⑧记录状态           │  ┌───────┐ ││
                                       │           │─────────────────────▶│SQLite │ ││
                                       │           │                   │  └───────┘ ││
                                       │           │                   │           ││
                                       └───────────┘                   └───────────┘│
```

---

## 六、接口设计

### 6.1 内部模块接口

#### 6.1.1 相册采集器 IAlbumCrawler
```python
class IAlbumCrawler(ABC):
    """相册采集器接口"""
    
    @abstractmethod
    async def login(self) -> bool:
        """登录验证"""
        
    @abstractmethod
    async def fetch_new_photos(self, since: datetime) -> List[Photo]:
        """获取指定时间之后的新增照片"""
        
    @abstractmethod
    async def download_photo(self, photo: Photo, save_path: str) -> str:
        """下载照片到本地,返回本地路径"""
    
    @abstractmethod
    async def get_album_list(self) -> List[AlbumInfo]:
        """获取相册列表"""
```

#### 6.1.2 人脸识别引擎（可插拔架构）
> 完整接口定义、插件注册机制、工厂模式、4个内置Provider规格详见 **4.2节**

**快速索引:**
| 内容 | 所在章节 |
|------|---------|
| IFaceRecognizer 抽象接口(完整Python代码) | 4.2.2 |
| 数据模型(RecognitionResult/TargetConfig等) | 4.2.2 |
| 异常体系(FaceRecognizerError子类) | 4.2.2 |
| Registry注册表 + 工厂模式 | 4.2.3 |
| FaceRecognizerFacade 门面类 | 4.2.3 |
| TencentCloudProvider 实现规格 | 4.2.4 Provider A |
| BaiduProvider 实现规格 | 4.2.4 Provider B |
| InsightFaceLocalProvider 实现规格 | 4.2.4 Provider C |
| FacePlusProvider 实现规格 | 4.2.4 Provider D |
| 切换提供商操作指南(含自定义开发) | 4.2.5 |
| 目录结构与文件组织 | 4.2.4 |

**切换示例:**
```yaml
# config.yaml 中只需改 provider 字段:
face_recognition:
  provider: "tencent_cloud"   # → 改为 "baidu" 即可切换到百度
  # ... 各自的配置段 ...
```

#### 6.1.3 存储管理器 IStorageManager
```python
class IStorageManager(ABC):
    """存储管理器接口"""
    
    @abstractmethod
    def organize_photo(
        self, 
        photo: Photo, 
        recognition_result: RecognitionResult
    ) -> StoredPhotoInfo:
        """按规则整理照片到对应目录"""
    
    @abstractmethod
    def generate_metadata(self, date: date, photos: List[StoredPhotoInfo]) -> str:
        """生成当日元数据JSON文件"""
    
    @abstractmethod
    def get_storage_stats(self) -> StorageStats:
        """获取存储统计信息"""

class StoredPhotoInfo:
    file_path: str
    file_size: int
    original_filename: string
    stored_at: datetime
```

### 6.2 外部API对接

#### 6.2.1 腾讯云人脸识别API
```yaml
接口: DetectFace + SearchFaces
端点: https://iai.ap-guangzhou.tencentcloudapi.com/

关键参数:
  - MaxFaceNum: 10 (单图最多检测人脸数)
  - MinFaceSize: 34 (最小人脸尺寸)
  - MatchThreshold: 80 (匹配阈值)
  
限流:
  - 免费版: 1000次/月
  - 付费版: 按QPS计费
```

#### 6.2.2 QQ相关接口
```yaml
注意: QQ官方未公开群相册API,需通过以下方式实现:

方案A (推荐): 使用浏览器Cookie模拟请求
  - 登录 web.qq.com 获取 Cookie
  - 通过 HTTP 请求访问群相册页面解析数据
  - 风险: Cookie过期需重新登录
  
方案B: 使用第三方协议库
  - go-cqhttp / Lagrange.Core 等
  - 提供标准化的API接口
  - 风险: 可能违反QQ使用条款

方案C (最稳定): 浏览器插件辅助
  - 开发Chrome/Edge插件监听相册加载事件
  - 通过本地HTTP服务接收数据
  - 需保持浏览器运行
```

---

## 七、数据处理流程

### 7.1 主处理流程(时序图风格)
```
时间轴 ──────────────────────────────────────────────────────────▶

[调度器]     [采集器]     [识别引擎]     [存储器]     [通知器]
  │            │            │             │            │
  │ 触发任务    │            │             │            │
  │────────────▶│            │             │            │
  │            │            │             │            │
  │            │ 查询新增照片│             │            │
  │            │─────────────────────────▶│            │
  │            │            │             │            │
  │            │ 返回照片列表│             │            │
  │            │◀──────────────────────────│            │
  │            │            │             │            │
  │            │ 逐张处理:   │             │            │
  │            │  下载照片   │             │            │
  │            │────────────▶            │            │
  │            │            │             │            │
  │            │            │  人脸识别    │            │
  │            │            │────────────▶│            │
  │            │            │             │            │
  │            │            │  返回结果    │            │
  │            │            │◀────────────│            │
  │            │            │             │            │
  │            │  包含目标?  │             │            │
  │            │──是────────▶│  归档存储   │            │
  │            │            │────────────▶│            │
  │            │            │             │            │
  │            │            │             │ 发送通知    │
  │            │            │             │────────────▶│
  │            │            │             │            │
  │  任务完成  │            │             │            │
  │◀───────────│            │             │            │
```

### 7.2 异常处理流程
```
┌────────────────┐
│    发生异常     │
└───────┬────────┘
        │
        ▼
┌──────────────────┐     是     ┌──────────────┐
│ 网络超时/错误?    │───────────▶│ 指数退避重试  │
└───────┬──────────┘            │ (最多3次)    │
        │否                     └──────┬───────┘
        ▲                              │失败
        │                               ▼
┌───────┴──────────┐           ┌──────────────┐
│ Cookie失效?      │──是──────▶│ 告警:需重新   │
└───────┬──────────┘           │ 登录QQ       │
        │否                    └──────┬───────┘
        ▲                              │
        │                               │
┌───────┴──────────┐           ┌───────▼───────┐
│ API配额耗尽?     │──是──────▶│ 告警:配额不足  │
└───────┬──────────┘           │ 等待次日重置  │
        │否                    └───────────────┘
        │
        ▼
┌──────────────┐
│ 记录错误日志  │
│ 跳过该照片    │
│ 继续下一张    │
└──────────────┘
```

---

## 八、运营与监控

### 8.1 关键指标(KPI)

| 指标名称 | 定义 | 目标值 | 监控频率 |
|---------|------|--------|---------|
| 采集成功率 | 成功采集照片数 / 总应采集数 | ≥99% | 每日 |
| 识别准确率 | 正确识别包含目标的照片数 / 实际包含总数 | ≥95% | 每周抽检 |
| 漏检率 | 未识别出的含目标照片数 / 实际包含总数 | ≤2% | 每周抽检 |
| 处理及时率 | 照片上传后2小时内完成处理的占比 | ≥95% | 每日 |
| 系统可用性 | 正常运行时间 / 总时间 | ≥99% | 实时 |

### 8.2 日志规范
```yaml
日志级别定义:
  DEBUG: 详细调试信息(每张照片的处理细节)
  INFO:  正常业务流程(开始/结束任务,发现新照片)
  WARN:  需要注意的情况(Cookie即将过期,配额使用超过80%)
  ERROR: 错误情况(API调用失败,文件写入失败)

日志格式:
  "{timestamp} [{level}] [{module}] {message} {extra}"

示例:
  "2026-04-16 18:30:05 [INFO] [crawler] 发现3张新照片,开始处理"
  "2026-04-16 18:30:06 [INFO] [recognizer] 照片IMG_002识别通过,置信度:0.96"
  "2026-04-16 18:30:07 [WARN] [api] 腾讯云API剩余配额:156次(15.6%)"
  "2026-04-16 18:30:08 [ERROR] [storage] 写入文件失败:Disk full"
```

### 8.3 通知策略

| 场景 | 通知级别 | 通知内容示例 | 推送渠道 |
|-----|---------|-------------|---------|
| 发现新照片 | INFO | "今天发现12张宝贝的新照片 📸" | 微信/邮件 |
| 处理完成 | INFO | "今日处理完毕:共45张,其中宝贝的12张" | 微信(每日汇总) |
| Cookie即将过期 | WARN | "QQ Cookie将在3天后过期,请及时更新" | 微信 |
| API配额不足 | WARN | "人脸识别配额剩余15%,请注意" | 微信 |
| 连续失败 | ERROR | "连续3次采集失败,请检查网络和Cookie" | 微信+邮件 |
| 磁盘空间不足 | ERROR | "照片存储盘剩余空间<5GB" | 微信+邮件 |

---

## 九、部署方案

### 9.1 部署架构
```
推荐: 家庭NAS / 旧笔记本 / 云服务器(可选)

最低配置要求:
  CPU: 2核及以上
  内存: 4GB及以上
  硬盘: 至少100GB空闲(SSD推荐)
  网络: 稳定的互联网连接
  系统: Windows 10/11 或 Linux (Ubuntu 20.04+)

软件环境:
  - Python 3.10+
  - 腾讯云SDK (pip install tencentcloud-sdk-python)
  - 其他依赖见 requirements.txt
```

### 9.2 安装步骤
```bash
# 1. 克隆/下载项目代码
git clone <repo_url>
cd CrawlPhotos

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置文件
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml 填入实际配置

# 5. 准备参考照片
mkdir config/reference_photos/daughter/
# 将宝宝的10-20张清晰正面照放入该目录

# 6. 初始化数据库
python -m app.db.init

# 7. 首次运行(测试模式)
python main.py --test

# 8. 设置开机自启(Windows计划任务 / Linux systemd)
# 参考部署文档
```

### 9.3 开机自启配置
```ini
; Windows计划任务 (taskschd.msc)
; 触发器: 系统启动时
; 操作: python D:\CrawlPhotos\main.py
; 条件: 仅当用户登录时(或不管用户是否登录)

# Linux systemd 服务 (/etc/systemd/system/baby-photos.service)
[Unit]
Description=Baby Photos Auto Crawler
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/opt/CrawlPhotos
ExecStart=/opt/CrawlPhotos/venv/bin/python /opt/CrawlPhotos/main.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

---

## 十、安全与隐私

### 10.1 数据安全措施

| 安全维度 | 措施 |
|---------|------|
| QQ账号安全 | Cookie加密存储,权限最小化,定期提醒更新 |
| API密钥管理 | 使用环境变量存储SecretId/Key,不写入代码仓库 |
| 照片隐私 | 所有数据仅在本地处理,不上传至第三方(除人脸API必需) |
| 网络安全 | HTTPS通信,敏感信息不在日志中打印 |
| 访问控制 | 本地存储目录可设置NTFS/FACL权限控制 |

### 10.2 隐私合规
- 所有照片仅用于个人家庭用途,不对外分享(除非主动开启分享功能)
- 腾讯云人脸识别API的数据处理遵循其隐私政策
- 用户可随时清除本地数据和云端配置
- 不收集任何除必要功能外的用户信息

---

## 十一、里程碑规划

### Phase 1: MVP核心 (Week 1-2)
- [x] PRD V1.0 文档编写
- [x] PRD V1.1 补充需求(触发方式/去重/小程序规划)
- [x] PRD V1.2 人脸识别可插拔架构设计
- [ ] QQ群相册照片采集基础功能(Cookie模拟)
- [ ] **人脸识别可插拔框架**: IFaceRecognizer接口 + Registry注册表 + Facade门面 + 工厂模式
- [ ] **Provider实现A**: TencentCloudProvider(腾讯云,默认提供商)
- [ ] 本地按月归档存储
- [ ] 基础配置管理(YAML)
- [ ] **三种触发模式**: 事件触发 + 定时触发 + CLI手动触发
- [ ] **基础去重**: 数据库级别(photo_id唯一索引)

### Phase 2: 稳定性与去重增强 + 多Provider (Week 3-4)
- [ ] **三层去重机制完善**: 内存Set + SQLite + SHA256 Hash
- [ ] **Provider实现B**: BaiduProvider(百度AI人脸识别)
- [ ] **Provider实现C**: InsightFaceLocalProvider(本地离线模型)
- [ ] 照片全生命周期状态机(pending->downloaded->...->completed)
- [ ] 上传去重队列(personal_photo_id防重复上传)
- [ ] 异常处理与指数退避重试(最多3次)
- [ ] 日志系统搭建(loguru + 自动轮转)
- [ ] Cookie有效期检测与到期预警
- [ ] 数据一致性自检(数据库 vs 文件系统)
- [ ] 企业微信通知集成

### Phase 3: 增值功能 (Week 5-6)
- [ ] 个人QQ相册自动上传(含失败重试队列)
- [ ] 多目标人物支持(多孩子场景)
- [ ] 参考照片自动更新机制(孩子长相变化适应)
- [ ] API服务层(FastAPI,为V2.0铺路,默认关闭)

### Phase 4: 浏览与管理界面 (Week 7-8)
- [ ] **本地H5 Web界面** (照片瀑布流 + 日历视图 + 统计面板)
- [ ] Web端手动触发按钮 + 系统状态仪表盘
- [ ] 照片大图预览(缩略图/原图切换)
- [ ] 打包为Windows exe安装程序(PyInstaller)
- [ ] 开机自启一键配置 + 配置向导
- [ ] 使用文档与FAQ

### Phase 5: 微信小程序 (Week 9-12, 后续迭代)
- [ ] 微信小程序项目初始化(TDesign组件库)
- [ ] 小程序API对接(HTTPS调用FastAPI后端)
- [ ] 首页瀑布流 + 月历热力图 + 照片详情页
- [ ] 统计概览页 + 手动触发筛选按钮
- [ ] 微信订阅消息推送 + 照片保存到手机
- [ ] 分享海报生成功能
- [ ] 域名备案 + HTTPS证书 + 审核发布

---

## 十二、风险与应对

| 风险类别 | 风险描述 | 概率 | 影响 | 应对措施 |
|---------|---------|------|------|---------|
| 技术风险 | QQ协议变更导致采集失败 | 高 | 高 | 设计可替换采集器架构;准备浏览器插件备用方案 |
| 技术风险 | 人脸识别API涨价/限额 | 低 | 中 | 预留本地模型切换能力;多供应商备选 |
| 运维风险 | 机器断电/网络中断 | 中 | 中 | 开机自启+断网重试+异常告警 |
| 隐私风险 | Cookie泄露导致QQ被盗 | 低 | 高 | 加密存储+本地使用+定期更换提醒 |
| 误判风险 | 重要照片被漏检 | 中 | 高 | 低阈值兜底+人工审核模式+每日报告 |

---

## 附录

### A. 术语表
| 术语 | 说明 |
|-----|------|
| QQ群相册 | QQ群内置的相册功能,用于共享照片 |
| 人脸特征向量 | 将人脸图像转换为一串数值表示,用于相似度计算 |
| 置信度 | 人工智能模型对判断结果的把握程度(0~1) |
| Cookie | 浏览器存储的登录凭证,用于身份验证 |
| Cron表达式 | 一种时间表达式语法,用于定义周期性任务的执行时间 |

### B. 参考资源
- 腾讯云人脸识别文档: https://cloud.tencent.com/product/facerecognition
- APScheduler文档: https://apscheduler.readthedocs.io/
- QQ相关协议研究: https://github.com/MrHestia/LagrangeCore

### C. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|-----|------|---------|------|
| V1.2 | 2026-04-16 | 人脸识别模块重构为可插拔架构(IFaceRecognizer接口+注册表+工厂+门面,支持腾讯云/百度/InsightFace/Face++一行配置切换) | Product Team |
| V1.1 | 2026-04-16 | 补充:三种触发模式/三层去重机制/小程序规划/API接口定义 | Product Team |
| V1.0 | 2026-04-16 | 初始版本,完成PRD编写 | Product Team |
