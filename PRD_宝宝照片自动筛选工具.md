# 宝宝照片自动筛选工具 - 产品需求文档 (PRD)

| 文档版本 | V1.3 | 状态 | 修订 |
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
- [x] PRD V1.3 架构优化与增强方案(采集器可插拔/事件总线/熔断降级等)
- [ ] QQ群相册照片采集基础功能(Cookie模拟)
- [ ] **人脸识别可插拔框架**: IFaceRecognizer接口 + Registry注册表 + Facade门面 + 工厂模式
- [ ] **Provider实现A**: TencentCloudProvider(腾讯云,默认提供商)
- [ ] 本地按月归档存储
- [ ] 基础配置管理(YAML)
- [ ] **三种触发模式**: 事件触发 + 定时触发 + CLI手动触发
- [ ] **基础去重**: 数据库级别(photo_id唯一索引)
- [ ] **图片预处理管道**: EXIF方向校正 + 格式转换 + 智能缩放 + 质量压缩

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
- [ ] **事件总线(EventBus)**: 模块间发布-订阅解耦
- [ ] **采集器可插拔架构**: IAlbumCrawler接口 + Registry + Facade(对齐人脸识别)

### Phase 3: 增值功能 + 可靠性增强 (Week 5-6)
- [ ] 个人QQ相册自动上传(含失败重试队列)
- [ ] 多目标人物支持(多孩子场景)
- [ ] 参考照片自动更新机制(孩子长相变化适应)
- [ ] API服务层(FastAPI,为V2.0铺路,默认关闭)
- [ ] **任务队列持久化**: SQLite-based Queue + 状态机 + 死信队列(DLQ)
- [ ] **熔断器+限流+降级**: 三级防护体系保护外部API调用
- [ ] **识别结果缓存层**: 避免重复API调用,节省配额

### Phase 4: 浏览与管理界面 + 质量保障 (Week 7-8)
- [ ] **本地H5 Web界面** (照片瀑布流 + 日历视图 + 统计面板)
- [ ] Web端手动触发按钮 + 系统状态仪表盘
- [ ] 照片大图预览(缩略图/原图切换)
- [ ] 打包为Windows exe安装程序(PyInstaller)
- [ ] 开机自启一键配置 + **配置向导** (--setup模式)
- [ ] 使用文档与FAQ
- [ ] **双阈值+人工审核池**: 降低漏检率,边缘案例兜底
- [ ] **结构化Metrics收集**: Counter/Gauge/Histogram + SQLite存储

### Phase 5: 微信小程序 + 运维完善 (Week 9-12, 后续迭代)
- [ ] 微信小程序项目初始化(TDesign组件库)
- [ ] 小程序API对接(HTTPS调用FastAPI后端)
- [ ] 首页瀑布流 + 月历热力图 + 照片详情页
- [ ] 统计概览页 + 手动触发筛选按钮
- [ ] 微信订阅消息推送 + 照片保存到手机
- [ ] 分享海报生成功能
- [ ] 域名备案 + HTTPS证书 + 审核发布
- [ ] **存储后端可插拔**: IStorageBackend接口(本地/COS/OSS/NAS)
- [ ] **Docker化部署**: Dockerfile + docker-compose + Grafana监控
- [ ] **安全增强**: 敏感配置加密 + 操作审计日志 + API鉴权
- [ ] TraceID链路追踪: 全链路日志关联

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
| V1.3 | 2026-04-16 | 新增架构优化与增强方案(十三): 采集器/存储器可插拔、事件总线、熔断降级、任务队列、图片预处理、可观测性、安全增强、部署优化等系统性补充; 需求与方案分离呈现 | Architecture Team |
| V1.2 | 2026-04-16 | 人脸识别模块重构为可插拔架构(IFaceRecognizer接口+注册表+工厂+门面,支持腾讯云/百度/InsightFace/Face++一行配置切换) | Product Team |
| V1.1 | 2026-04-16 | 补充:三种触发模式/三层去重机制/小程序规划/API接口定义 | Product Team |
| V1.0 | 2026-04-16 | 初始版本,完成PRD编写 | Product Team |

---

## 十三、架构优化与增强方案（V1.3 补充）

> **定位**: 本章节为资深架构师基于V1.2 PRD的**架构评审意见与增强方案**,聚焦于
> 生产就绪度、长期演进能力和系统健壮性。
>
> **组织方式**: 每个优化项按「需求动机 → 架构方案 → 实施细节」结构化呈现。

---

### 13.1 采集器可插拔架构（对齐人脸识别设计）

#### 13.1.1 需求动机

| 维度 | 说明 |
|------|------|
| **现状问题** | 人脸识别模块已完成Strategy + Registry + Factory + Facade的完整可插拔设计,
但`IAlbumCrawler`仅定义了基础接口,**缺少同等力度的可插拔支撑** |
| **风险等级** | PRD十二、风险与应对章节标注: QQ协议变更导致采集失败 = 「高概率 / 高影响」 |
| **影响范围** | 一旦QQ协议变更或Cookie模拟方案失效,需大幅改动业务代码才能切换采集方式 |

#### 13.1.2 架构方案 — CrawlerRegistry + 工厂模式

```
app/
  crawler/                              # 相册采集模块 (对标 face_recognition)
    interfaces.py                       # IAlbumCrawler 抽象接口
    models.py                           # Photo / AlbumInfo 数据模型
    exceptions.py                       # CookieExpiredError / RateLimitError 等
    registry.py                         # CrawlerRegistry 注册表 + 工厂
    facade.py                           # CrawlerFacade 门面类
    providers/
      __init__.py
      cookie_sim/                       # Provider A: Cookie模拟 (默认)
      ├── __init__.py
      └── provider.py                   # CookieSimCrawler
      lagrange_core/                    # Provider B: Lagrange.Core协议
      ├── __init__.py
      └── provider.py                   # LagrangeCoreCrawler
      browser_plugin/                   # Provider C: 浏览器插件辅助
      ├── __init__.py
      └── provider.py                   # BrowserPluginCrawler
```

#### 13.1.3 统一接口定义 (IAlbumCrawler 增强)

```python
class IAlbumCrawler(ABC):
    """相册采集器抽象接口 - 所有采集方式必须实现"""

    @property
    @abstractmethod
    def crawler_type(self) -> CrawlerType:
        """返回此实现的爬虫类型标识"""
        pass

    @property
    @abstractmethod
    def crawler_info(self) -> CrawlerInfo:
        """返回爬虫能力描述信息"""
        pass

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化采集器 (登录/建立连接等)

        Returns:
            初始化是否成功

        Raises:
            CookieExpiredError: Cookie已失效,需用户重新登录
            NetworkError: 网络连接失败
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            {
                "healthy": bool,
                "cookie_expires_in_days": Optional[int],
                "latency_ms": float,
                "message": str
            }
        """
        pass

    @abstractmethod
    async def fetch_album_list(self) -> List[AlbumInfo]:
        """获取相册列表"""
        pass

    @abstractmethod
    async def fetch_new_photos(
        self,
        album_id: str,
        since: datetime
    ) -> List[Photo]:
        """获取指定时间之后的新增照片"""
        pass

    @abstractmethod
    async def download_photo(
        self,
        photo: Photo,
        save_path: str,
        progress_callback: Optional[Callable] = None
    ) -> DownloadResult:
        """
        下载照片到本地

        Args:
            photo: 照片对象
            save_path: 保存路径
            progress_callback: 下载进度回调 (可选)

        Returns:
            DownloadResult: 包含本地路径、文件大小、下载耗时等信息
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源 (关闭连接/释放会话)"""
        pass


class CrawlerType(Enum):
    COOKIE_SIM = "cookie_sim"
    LAGRANGE_CORE = "lagrange_core"
    BROWSER_PLUGIN = "browser_plugin"
    CUSTOM = "custom"


@dataclass
class CrawlerInfo:
    crawler_type: CrawlerType
    display_name: str
    version: str
    requires_cookie: bool           # 是否需要Cookie
    supports_realtime: bool         # 是否支持实时监听
    cookie_refreshable: bool        # 是否支持自动刷新Cookie
    stability_rating: int           # 稳定性评分 (1-5)
    description: str
```

#### 13.1.4 内置 Provider 规格

##### Provider A: CookieSimCrawler (默认)

```yaml
crawler_type: cookie_sim
display_name: "Cookie模拟采集"
version: "1.0"
requires_cookie: true
supports_realtime: false          # 仅轮询模式
cookie_refreshable: false         # 需手动更新
stability_rating: 2               # 中低稳定性(Cookie易过期)

关键特性:
  ✅ 无需额外依赖,纯HTTP请求实现
  ✅ 实现简单,维护成本低
  ⚠️  Cookie有效期有限(通常数天~数周)
  ⚠️  QQ页面改版可能导致解析逻辑失效
  ❌  无法获取实时通知

实现要点:
  1. 使用httpx模拟浏览器请求 web.qq.com 获取Cookie
  2. 解析群相册HTML/JSON接口获取照片列表
  3. 定期检测Cookie有效性(health_check),即将过期时告警
```

##### Provider B: LagrangeCoreCrawler

```yaml
crawler_type: lagrange_core
display_name: "Lagrange.Core 协议采集"
version: "1.0"
requires_cookie: false             # 使用独立登录态
supports_realtime: true            # 支持消息监听
cookie_refreshable: true           # 自动刷新Token
stability_rating: 4                 # 较高稳定性

关键特性:
  ✅ 支持实时消息监听(事件触发A的核心支撑)
  ✅ 自动Token续期,无需手动干预
  ✅ 标准化API接口,不依赖页面解析
  ⚠️  依赖第三方协议库(Lagrange.Core)
  ⚠️  可能违反QQ使用条款(仅限个人使用场景)

实现要点:
  1. 启动Lagrange.Core实例(或连接已有实例)
  2. 监听群消息,正则匹配相册上传通知
  3. 通过API调用获取相册照片列表和下载链接
  4. 与EventBus联动,收到通知即触发采集任务
```

##### Provider C: BrowserPluginCrawler

```yaml
crawler_type: browser_plugin
display_name: "浏览器插件辅助采集"
version: "1.0"
requires_cookie: true              # 复用浏览器登录态
supports_realtime: true            # DOM变化监听
cookie_refreshable: true           # 浏览器保持登录即可
stability_rating: 5                 # 最高稳定性

关键特性:
  ✅ 最稳定: 直接使用浏览器登录态,不存在独立Cookie失效问题
  ✅ 支持DOM实时监听(MutationObserver)
  ⚠️  需要保持浏览器运行并打开指定页面
  ⚠️  需要额外开发Chrome/Edge扩展

实现要点:
  1. 开发浏览器扩展(MV3),注入到QQ群相册页面
  2. 监听DOM变化(新照片加载),通过WebSocket发送到本地HTTP服务
  3. 本地服务接收数据后写入统一任务队列
```

#### 13.1.5 切换采集器的操作指南

```bash
# config.yaml 中修改 crawler.provider 即可:

# 方式1: Cookie模拟 (默认)
crawler:
  provider: "cookie_sim"              # <-- 只改这里!
  cookie_sim:
    cookies_file: "data/qq_cookies.txt"

# 方式2: Lagrange.Core (推荐用于事件触发)
crawler:
  provider: "lagrange_core"
  lagrange_core:
    ws_url: "ws://127.0.0.1:8080"
    bot_qq: "你的机器人QQ号"
    group_id: "123456789"

# 方式3: 浏览器插件 (最稳定)
crawler:
  provider: "browser_plugin"
  browser_plugin:
    listen_port: 9876               # 本地HTTP服务端口
```

#### 13.1.6 配置文件新增段

```yaml
# ==================== 采集器配置（可插拔） ====================
crawler:
  # ====== 核心切换开关: 只需改这一行! ======
  provider: "cookie_sim"
  # 可选值:
  #   "cookie_sim"       - Cookie模拟 (默认,最简单)
  #   "lagrange_core"    - Lagrange.Core协议 (支持实时事件触发)
  #   "browser_plugin"   - 浏览器插件 (最稳定,需保持浏览器运行)

  # ====== Provider A: Cookie模拟 ======
  cookie_sim:
    cookies_file: "data/qq_cookies.txt"
    login_url: "https://xui.ptlogin2.qq.com/"
    cookie_check_interval_hours: 6     # Cookie有效性检查间隔

  # ====== Provider B: Lagrange.Core ======
  lagrange_core:
    ws_url: "ws://127.0.0.1:8080"
    bot_qq: ""
    group_id: ""
    reconnect_interval_seconds: 30     # 断线重连间隔
    event_debounce_seconds: 60         # 同批次上传防抖等待

  # ====== Provider C: 浏览器插件 ======
  browser_plugin:
    listen_port: 9876
    allowed_origins: ["chrome-extension://*"]
```

---

### 13.2 存储后端可插拔抽象

#### 13.2.1 需求动机

| 维度 | 说明 |
|------|------|
| **现状问题** | `IStorageManager` 和 `IStorageBackend` 仅面向本地文件系统硬编码实现 |
| **演进需求** | 用户照片持续增长(每年数千张),未来可能迁移至 NAS / 云存储(COS/OSS/S3) |
| **设计原则** | 存储位置对上层业务透明,切换存储后端零代码改动 |

#### 13.2.2 架构方案 — IStorageBackend 接口

```python
class IStorageBackend(ABC):
    """存储后端抽象 - 本地/云端/NAS 统一接口"""

    @property
    @abstractmethod
    def backend_type(self) -> StorageBackendType:
        """返回存储后端类型标识"""
        pass

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化存储后端 (建立连接/验证权限/创建桶等)"""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查 (可用性/空间/配额)

        Returns:
            {
                "healthy": bool,
                "total_space_bytes": int,
                "used_space_bytes": int,
                "free_space_bytes": int,
                "utilization_percent": float,
                "message": str
            }
        """
        pass

    @abstractmethod
    async def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "image/jpeg",
        metadata: Optional[Dict] = None
    ) -> StoredFileRef:
        """
        保存文件

        Args:
            key: 存储键路径 (如 "2026/04_April/2026-04-16/20260416_0001.jpg")
            data: 文件二进制数据
            content_type: MIME类型
            metadata: 附加元数据

        Returns:
            StoredFileRef: 包含访问路径、大小、ETag等引用信息
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """读取文件内容"""
        pass

    @abstractmethod
    async def get_stream(self, key: str):
        """流式读取 (大文件用)"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除文件"""
        pass

    @abstractmethod
    async def list_files(
        self,
        prefix: str,
        recursive: bool = False
    ) -> List[StoredFileRef]:
        """列出目录下的文件"""
        pass

    @abstractmethod
    async def get_stats(self) -> StorageStats:
        """获取存储统计信息"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass


class StorageBackendType(Enum):
    LOCAL = "local"                     # 本地文件系统
    COS = "cos"                         # 腾讯云COS
    OSS = "oss"                         # 阿里云OSS
    S3 = "s3"                           # AWS S3兼容 (MinIO/NAS)
    NAS = "nas"                          # NAS挂载 (SMB/NFS)


@dataclass
class StoredFileRef:
    key: str                            # 存储键
    url: Optional[str]                  # 可公开访问的URL(如有)
    size_bytes: int
    etag: Optional[str]
    last_modified: datetime
    content_type: str
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class StorageStats:
    total_files: int
    total_size_bytes: int
    used_space_bytes: int
    free_space_bytes: int
    utilization_percent: float
    oldest_file_date: Optional[datetime]
    newest_file_date: Optional[datetime]
```

#### 13.2.3 内置存储后端规格

##### LocalStorageBackend (默认, MVP阶段)

```yaml
backend_type: local
display_name: "本地文件系统"
特点:
  - 零依赖,开箱即用
  - 目录结构按 {year}/{month}_{name}/{date} 组织
  - 自动生成 metadata.json 元数据文件
  - 支持磁盘空间监控和预警阈值

配置示例:
storage:
  backend: "local"
  local:
    root_directory: "D:/BabyPhotos"
    directory_format: "{root}/{year}/{month_num}_{month_name}/{date}"
    disk_warning_threshold_gb: 20      # 剩余<20GB时告警
    disk_critical_threshold_gb: 5       # 剩余<5GB时严重告警
```

##### CosStorageBackend (腾讯云COS, Phase 3+)

```yaml
backend_type: cos
display_name: "腾讯云对象存储(COS)"
特点:
  - 无限容量,按量付费(约0.118元/GB/月)
  - CDN加速分发,适合多设备访问
  - 自动生命周期管理(冷热分层)
  - 支持跨地域复制备份

配置示例:
storage:
  backend: "cos"
  cos:
    secret_id: "${COS_SECRET_ID}"
    secret_key: "${COS_SECRET_KEY}"
    region: "ap-guangzhou"
    bucket: "baby-photos-1234567890"
    cdn_domain: "cdn.example.com"       # 可选,自定义CDN域名
    lifecycle_days: 365                 # 365天后自动转低频存储
```

---

### 13.3 事件总线 (EventBus) — 模块间解耦

#### 13.3.1 需求动机

| 维度 | 说明 |
|------|------|
| **现状问题** | 从数据流图(五、5.3节)可见,识别完成后依次调用 存储→上传→通知,
形成**隐式链式依赖**。增加新消费者必须改动主流程代码 |
| **演进需求** | 未来可能新增: 同时推送到家庭群、生成成长报告、AI标签分类等功能 |
| **设计原则** | 发布-订阅模式,生产者与消费者完全解耦,新增功能只需添加订阅者 |

#### 13.3.2 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                      事件总线 (EventBus)                       │
│                                                              │
│   ┌─────────────┐                                            │
│   │  EventRouter │ ◀── 统一的事件路由与分发                     │
│   └──────┬──────┘                                            │
│          │                                                    │
│   ┌──────┴──────────────────────────────────────┐            │
│   │              订阅者 (Subscriber)             │            │
│   │                                             │            │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │            │
│   │  │存储订阅器  │  │上传订阅器  │  │通知订阅器  │  │            │
│   │  │on_photo_  │  │on_photo_  │  │on_photo_  │  │            │
│   │  │recognized │  │stored    │  │uploaded  │  │            │
│   │  └──────────┘  └──────────┘  └──────────┘  │            │
│   │                                             │            │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │            │ ← 可扩展
│   │  │统计订阅器  │  │审核池订阅器│  │审计日志   │  │            │
│   │  └──────────┘  └──────────┘  └──────────┘  │            │
│   └─────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

#### 13.3.3 事件类型定义

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum


class EventType(Enum):
    """系统事件类型枚举"""
    # 采集相关
    PHOTO_DISCOVERED = "photo.discovered"           # 发现新照片
    PHOTO_DOWNLOADED = "photo.downloaded"           # 照片下载完成
    PHOTO_DOWNLOAD_FAILED = "photo.download_failed"  # 下载失败

    # 识别相关
    PHOTO_RECOGNIZED = "photo.recognized"           # 识别完成
    PHOTO_TARGET_FOUND = "photo.target_found"       # 发现目标人物
    PHOTO_TARGET_NOT_FOUND = "photo.target_not_found"# 未发现目标
    PHOTO_NO_FACE = "photo.no_face"                 # 未检测到人脸

    # 存储相关
    PHOTO_STORED = "photo.stored"                   # 归档完成
    PHOTO_SKIPPED = "photo.skipped"                 # 跳过(重复等)

    # 上传相关
    PHOTO_UPLOADED = "photo.uploaded"              # 上传完成
    PHOTO_UPLOAD_FAILED = "photo.upload_failed"     # 上传失败

    # 系统相关
    TASK_STARTED = "task.started"                   # 任务开始
    TASK_COMPLETED = "task.completed"              # 任务完成
    TASK_FAILED = "task.failed"                    # 任务失败
    SYSTEM_HEALTH_CHANGED = "system.health_changed" # 健康状态变化
    CONFIG_CHANGED = "system.config_changed"       # 配置变更


@dataclass
class BaseEvent:
    """所有事件的基类"""
    event_type: EventType
    trace_id: str                        # 关联的追踪ID
    timestamp: datetime
    source: str                          # 触发来源模块名
    payload: Dict[str, Any]              # 事件负载数据


# ---------- 具体事件定义 ----------

@dataclass
class PhotoDiscoveredEvent(BaseEvent):
    """发现新照片事件"""
    photo_id: str
    album_id: str
    upload_time: datetime
    uploader: str
    url: str


@dataclass
class PhotoRecognizedEvent(BaseEvent):
    """照片识别完成事件"""
    photo_id: str
    file_path: str
    recognition_result: Dict            # RecognitionResult序列化
    contains_target: bool
    confidence: float
    face_count: int


@dataclass
class PhotoTargetFoundEvent(BaseEvent):
    """目标人物匹配成功事件"""
    photo_id: str
    target_name: str
    confidence: float
    face_box: Dict                     # BoundingBox序列化


@dataclass
class PhotoStoredEvent(BaseEvent):
    """照片归档完成事件"""
    photo_id: str
    local_path: str
    storage_backend: str
    file_size: int
    directory: str                     # 归档目录


@dataclass
class PhotoUploadedEvent(BaseEvent):
    """照片上传个人相册完成事件"""
    photo_id: str
    personal_album_id: str
    personal_photo_id: str
    uploaded_at: datetime
```

#### 13.3.4 EventBus 实现

```python
import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable, List, Set

logger = logging.getLogger(__name__)

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventBus:
    """
    轻量级异步事件总线

    设计原则:
    - 发布者与订阅者完全解耦
    - 支持同步/异步混合订阅者
    - 保证同一事件内订阅者执行顺序(有序广播)
    - 单个订阅者异常不影响其他订阅者(故障隔离)
    """

    def __init__(self):
        # EventType -> [handler, ...] 的映射
        self._subscribers: Dict[EventType, List[EventHandler]] = defaultdict(list)
        # 全局通配符订阅 (* 匹配所有事件)
        self._global_subscribers: List[EventHandler] = []
        self._lock = asyncio.Lock()
        self._event_history: List[BaseEvent] = []       # 最近N条事件记录(用于调试)
        self._max_history: int = 1000

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler
    ) -> Callable[[], None]:
        """
        订阅事件

        Returns:
            取消订阅的函数(方便用装饰器语法)

        用法:
            @event_bus.subscribe(EventType.PHOTO_RECOGNIZED)
            async def on_recognized(event: PhotoRecognizedEvent):
                ...
        """
        self._subscribers[event_type].append(handler)

        def unsubscribe():
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass

        return unsubscribe

    def subscribe_all(self, handler: EventHandler) -> Callable[[], None]:
        """订阅所有事件 (全局监听,如审计日志)"""
        self._global_subscribers.append(handler)

        def unsubscribe():
            try:
                self._global_subscribers.remove(handler)
            except ValueError:
                pass

        return unsubscribe

    async def publish(self, event: BaseEvent) -> None:
        """
        发布事件 (广播给所有订阅者)

        异常处理策略:
        - 单个订阅者抛异常时捕获并记录,不影响其他订阅者
        - 所有异常汇总后在日志中输出完整报告
        """
        # 记录事件历史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        logger.debug(
            "发布事件: %s trace=%s source=%s",
            event.event_type.value, event.trace_id, event.source
        )

        errors = []

        # 1. 先发给该事件类型的专属订阅者
        for handler in self._subscribers.get(event.event_type, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "事件处理器异常: event=%s handler=%s error=%s",
                    event.event_type.value,
                    handler.__qualname__,
                    e,
                    exc_info=True
                )
                errors.append((handler.__qualname__, str(e)))

        # 2. 再发给全局订阅者
        for handler in self._global_subscribers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "全局事件处理器异常: event=%s handler=%s error=%s",
                    event.event_type.value,
                    handler.__qualname__,
                    e,
                    exc_info=True
                )
                errors.append((handler.__qualname__, str(e)))

        if errors:
            logger.warning(
                "事件 %s 处理完成, %d/%d 个处理器出现异常: %s",
                event.event_type.value,
                len(errors),
                len(self._subscribers.get(event.event_type, [])) +
                len(self._global_subscribers),
                [(n, err[:100]) for n, err in errors]
            )

    def get_recent_events(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 50
    ) -> List[BaseEvent]:
        """查询最近的事件记录(调试/运维用)"""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]
```

#### 13.3.5 业务集成示例 — 各模块如何接入

```python
# ========== 在主流程中发布事件 ==========

async def process_single_photo(photo: Photo, recognizer, storage, event_bus):
    """单张照片处理流程 (改造为事件驱动)"""

    # Step 1: 下载
    try:
        result = await downloader.download(photo)
        await event_bus.publish(PhotoDownloadedEvent(
            event_type=EventType.PHOTO_DOWNLOADED,
            trace_id=TraceContext.get_trace_id(),
            timestamp=datetime.now(),
            source="pipeline",
            payload={},
            photo_id=photo.photo_id,
            file_path=result.local_path,
            file_size=result.file_size
        ))
    except Exception as e:
        await event_bus.publish(BaseEvent(...))
        raise

    # Step 2: 识别
    recog_result = await recognizer.recognize(result.local_path)
    await event_bus.publish(PhotoRecognizedEvent(
        event_type=EventType.PHOTO_RECOGNIZED,
        ...,
        contains_target=recog_result.contains_target,
        confidence=recog_result.best_confidence,
        ...
    ))

    # 注意: 此处不再直接调用 storage.store() 和 uploader.upload()
    # 而是由各订阅者自行响应事件!


# ========== 存储模块作为独立订阅者 ==========

class StorageSubscriber:
    """存储模块 - 订阅识别结果事件,自动归档包含目标的照片"""

    def __init__(self, storage_manager: IStorageBackend, event_bus: EventBus):
        self._storage = storage_manager
        event_bus.subscribe(EventType.PHOTO_TARGET_FOUND, self.on_target_found)
        event_bus.subscribe(EventType.PHOTO_TARGET_NOT_FOUND, self.on_target_not_found)

    async def on_target_found(self, event: PhotoTargetFoundEvent):
        """发现目标照片 -> 归档存储"""
        stored = await self._storage.organize_and_save(event.payload["file_path"])
        await event_bus.publish(PhotoStoredEvent(
            event_type=EventType.PHOTO_STORED,
            ...,
            local_path=stored.file_path,
            file_size=stored.size_bytes,
            ...
        ))

    async def on_target_not_found(self, event: BaseEvent):
        """非目标照片 -> 可选择保留标记或丢弃"""
        # 根据 no_face_action 配置决定
        ...


# ========== 上传模块作为独立订阅者 ==========

class UploadSubscriber:
    """上传模块 - 订阅归档完成事件,自动上传到个人相册"""

    def __init__(self, uploader, event_bus: EventBus):
        self._uploader = uploader
        event_bus.subscribe(EventType.PHOTO_STORED, self.on_stored)

    async def on_stored(self, event: PhotoStoredEvent):
        """归档完成后 -> 上传个人相册"""
        if not self._uploader.enabled:
            return
        result = await self._uploader.upload_to_personal_album(
            event.local_path, event.directory
        )
        await event_bus.publish(PhotoUploadedEvent(...))


# ========== 通知模块作为独立订阅者 ==========

class NotificationSubscriber:
    """通知模块 - 订阅各类事件,聚合推送通知"""

    def __init__(self, notifier, event_bus: EventBus):
        self._notifier = notifier
        self._daily_stats = {"found": 0, "total": 0}
        event_bus.subscribe(EventType.PHOTO_TARGET_FOUND, self.on_new_found)
        event_bus.subscribe(EventType.TASK_COMPLETED, self.on_task_done)

    async def on_new_found(self, event: PhotoTargetFoundEvent):
        self._daily_stats["found"] += 1
        # 可在此处做即时通知(如果开启了即时推送)
        await self._notifier.send_instant(f"发现{event.target_name}的新照片! "
                                           f"置信度:{event.confidence:.0%}")

    async def on_task_done(self, event: BaseEvent):
        """任务完成 -> 发送每日汇总"""
        await self._notifier.send_daily_summary(self._daily_stats)
```

---

### 13.4 任务队列持久化 & 状态机

#### 13.4.1 需求动机

| 维度 | 说明 |
|------|------|
| **现状问题** | PRD四、4.6节提到了状态机和任务队列概念,**但缺少具体的持久化设计方案**。
程序崩溃重启后,处于中间态(pending→processing)的数据如何恢复? |
| **核心诉求** | 保证「精确一次处理语义」(Exactly-Once Semantics),
崩溃恢复后不丢失、不重复 |

#### 13.4.2 架构方案 — 基于 SQLite 的持久化任务队列

```sql
-- ==================== 任务队列表 ====================
CREATE TABLE IF NOT EXISTS task_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 任务基本信息
    task_type       TEXT NOT NULL,
    -- 值域: 'download' | 'recognize' | 'store' | 'upload' | 'full_pipeline'
    task_priority   INTEGER DEFAULT 0,         -- 数值越大优先级越高
    payload_json    TEXT NOT NULL,              -- JSON: 任务参数(照片信息等)

    -- 来源追踪
    trigger_type    TEXT NOT NULL DEFAULT 'manual',
    -- 'event'(事件触发) | 'scheduler'(定时) | 'manual'(手动)
    source_photo_id TEXT UNIQUE,               -- 关联的照片ID(去重依据)
    trace_id        TEXT,                      # 追踪ID

    -- 状态机字段
    status          TEXT NOT NULL DEFAULT 'pending',
    -- pending(待处理) -> processing(处理中) -> completed(已完成)
    -- pending -> processing -> failed(失败,可重试)
    -- pending -> skipped(跳过)
    -- processing -> timed_out(超时,强制回退到failed)

    -- 重试控制
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    next_retry_at   DATETIME,                   -- 指数退避下次重试时间
    error_class     TEXT,                       # 异常类名
    error_message   TEXT,                       # 错误详情
    error_stack     TEXT,                       # 堆栈信息(最近一次)

    -- 时间戳
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at      DATETIME,                   # 开始处理时间
    completed_at    DATETIME,                   # 完成时间

    -- 结果快照
    result_json     TEXT,                       -- 执行结果JSON(成功时)

    CONSTRAINT uq_task_photo UNIQUE (source_photo_id, task_type)
);

-- 状态索引
CREATE INDEX idx_task_status ON task_queue(status);
CREATE INDEX idx_task_retry ON task_queue(next_retry_at) WHERE status = 'failed';
CREATE INDEX idx_task_created ON task_queue(created_at);
CREATE INDEX idx_task_trigger ON task_queue(trigger_type);


-- ==================== 死信队列 (Dead Letter Queue) ====================
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    original_task_id INTEGER NOT NULL,          -- 原始任务ID
    task_type       TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    final_status    TEXT NOT NULL,               # 'exhausted'(耗尽重试) | 'poisoned'(毒丸)
    failure_count   INTEGER NOT NULL,
    last_error      TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    original_created_at DATETIME,               # 原始任务创建时间
    resolved        BOOLEAN DEFAULT FALSE,       # 是否已人工解决
    resolved_by     TEXT,                        # 解决人
    resolved_at     DATETIME,                    # 解决时间
    resolution_note TEXT                         # 解决备注
);
```

#### 13.4.3 任务状态机

```
                                    ┌─────────────┐
                              创建   │   pending    │◀──────────────────┐
                                    │  (待处理)    │                   │
                                    └──────┬───────┘                   │
                                           │ 取出执行                   │
                                           ▼                            │
                                    ┌─────────────┐                   │
                                    │  processing  │                   │
                                    │  (处理中)     │                   │
                                    └──────┬───────┘                   │
                                           │                            │
                    ┌──────────────────────┼──────────────────────┐     │
                    │ 成功                 │ 异常                   │     │
                    ▼                      ▼                        │     │
             ┌─────────────┐        ┌─────────────┐                │     │
             │  completed  │        │   failed    │                │     │
             │  (已完成)    │        │  (失败)     │                │     │
             └─────────────┘        └──────┬───────┘                │     │
                                          │                          │
                               ┌──────────┴──────────┐              │
                               │ retry < max_retries? │              │
                               ├──────────┬──────────┤              │
                              是│          否│        │              │
                               ▼           ▼         │              │
                    ┌─────────────┐ ┌─────────────┐  │              │
                    │  回退pending │ │ dead_letter │  │              │
                    │ (等待重试)   │ │ _queue(死信) │  │              │
                    └──────┬───────┘ └─────────────┘  │              │
                           │                          │              │
                           └──────────────────────────┘              │
                    (next_retry_at 到达后重新调度)                    │
                                                                    │
                    ┌────────────────────────────────┘
                    │
                    ▼
             ┌─────────────┐
             │  skipped    │◀─── 去重命中 / 不满足条件
             │  (跳过)     │
             └─────────────┘
```

#### 13.4.4 TaskQueueManager 实现

```python
class TaskQueueManager:
    """
    持久化任务队列管理器

    核心能力:
    - 原子入队 (带去重检查)
    - 可靠调度 (崩溃恢复)
    - 指数退避重试
    - 死信隔离
    """

    def __init__(self, db_session, event_bus: EventBus):
        self._db = db_session
        self._bus = event_bus

    async def enqueue(
        self,
        task_type: str,
        payload: Dict,
        source_photo_id: Optional[str] = None,
        trigger_type: str = "manual",
        priority: int = 0,
        max_retries: int = 3
    ) -> int:
        """
        入队 (原子性,带去重)

        Returns:
            task_id: 新建任务的ID (若已存在则返回已有任务ID)
        """
        # INSERT OR IGNORE 实现幂等入队
        sql = """
            INSERT OR IGNORE INTO task_queue
            (task_type, task_priority, payload_json, trigger_type,
             source_photo_id, trace_id, max_retries)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (...))
        task_id = cursor.lastrowid

        if cursor.rowcount == 0:
            # 已存在,查询已有任务ID
            existing = await self._db.execute(
                "SELECT id FROM task_queue WHERE source_photo_id=? AND task_type=?",
                (source_photo_id, task_type)
            )
            task_id = existing.fetchone()[0]

        return task_id

    async def dequeue(self, batch_size: int = 10) -> List[TaskItem]:
        """
        出队 (原子性,带锁机制防止并发重复消费)

        策略: UPDATE ... WHERE status='pending' ORDER BY priority DESC, id ASC LIMIT N
        """
        sql = """
            UPDATE task_queue
            SET status = 'processing',
                started_at = CURRENT_TIMESTAMP
            WHERE id IN (
                SELECT id FROM task_queue
                WHERE status = 'pending'
                  AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                ORDER BY task_priority DESC, id ASC
                LIMIT ?
            )
        """
        await self._db.execute(sql, (batch_size,))
        # 返回刚标记为 processing 的任务
        ...

    async def complete(self, task_id: int, result: Dict = None):
        """标记任务完成"""
        ...

    async def fail(self, task_id: int, error: Exception):
        """
        标记任务失败 (自动判断是否进入死信队列)
        
        - 若 retry_count < max_retries: 计算 next_retry_at (指数退避),回退到pending
        - 若 retry_count >= max_retries: 移入 dead_letter_queue
        """
        task = await self.get(task_id)
        new_retry = task.retry_count + 1

        if new_retry < task.max_retries:
            # 指数退避: 30s -> 60s -> 120s -> 240s
            delay = 30 * (2 ** task.retry_count)
            next_retry = datetime.now() + timedelta(seconds=delay)
            await self._db.execute("""
                UPDATE task_queue SET
                    status = 'pending',
                    retry_count = ?,
                    next_retry_at = ?,
                    error_class = ?,
                    error_message = ?
                WHERE id = ?
            """, (new_retry, next_retry, type(error).__name__, str(error), task_id))
        else:
            # 移入死信队列
            await self._move_to_dlq(task_id, error)

    async def recover_stale_tasks(self, timeout_minutes: int = 30):
        """
        恢复超时任务 (崩溃恢复核心方法)

        将 status='processing' 且 started_at 超过 timeout 分钟的任务
        强制回退为 pending 或 failed
        """
        stale_threshold = datetime.now() - timedelta(minutes=timeout_minutes)
        await self._db.execute("""
            UPDATE task_queue SET
                status = 'failed',
                error_message = 'Task timed out (stale recovery)',
                retry_count = retry_count + 1
            WHERE status = 'processing'
              AND started_at < ?
        """, (stale_threshold,))

    async def get_dead_letter_tasks(self, unresolved_only: bool = True):
        """查询死信队列中的任务(人工审核界面使用)"""
        ...

    async def resolve_dlq_task(self, dlq_id: int, action: str, note: str):
        """
        解决死信任务

        action: 'retry'(重新入队) | 'discard'(丢弃) | 'force_complete'
        """
        ...
```

---

### 13.5 熔断器、限流与降级三级防护

#### 13.5.1 需求动机

| 维度 | 说明 |
|------|------|
| **现状问题** | 当前PRD未涉及对外部API调用的任何保护措施。
一旦人脸识别API异常(超时/限流/宕机),可能导致级联故障,甚至耗尽免费配额 |
| **核心诉求** | 外部依赖故障时不拖垮主系统,且能自动/手动降级到备用方案 |

#### 13.5.2 三级防护体系

```
外部 API 调用请求
       │
       ▼
┌──────────────┐     超过 QPS 阈值?
│  ① 限流器     │────────是──▶ 排队等待 / 快速拒绝 (429 Too Many Requests)
│ RateLimiter   │
└──────┬───────┘
       │ 否 (放行)
       ▼
┌──────────────┐     连续失败 ≥ N 次?
│  ② 熔断器     │────────是──▶ Circuit Open → 快速失败 (无需真正调用API)
│ CircuitBreaker│
└──────┬───────┘
       │ 否 (Closed/HalfOpen, 正常调用)
       ▼
┌──────────────┐     主Provider异常?
│  ③ 降级器     │────────是──▶ 自动切换到备用Provider
│ Degradation   │               (腾讯云 → InsightFace本地模型)
└──────┬───────┘
       │
       ▼
  正常响应结果
```

#### 13.5.3 限流器 (Rate Limiter)

```python
class RateLimiter:
    """
    令牌桶算法限流器
    
    用途: 控制对单个API的QPS,避免触发平台侧限流
    例如: 腾讯云免费版QPS限制为5次/秒,此处设置为4次/秒留余量
    """

    def __init__(
        self,
        rate: float,           # 每秒填充速率 (tokens/sec)
        burst: int             # 桶容量 (最大突发请求数)
    ):
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> float:
        """
        获取令牌
        
        Returns:
            等待时间(秒),若立即获得则为0.0
            
        Raises:
            RateLimitExceededError: 等待超时时抛出
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._burst,
                self._tokens + elapsed * self._rate
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            # 计算需要等待的时间
            needed = tokens - self._tokens
            wait_time = needed / self._rate
            
            if wait_time > 30:  # 超过30s认为不可接受
                raise RateLimitExceededError(
                    f"Rate limit exceeded: need {wait_time:.1f}s wait"
                )
            
            # 等待令牌填充
            await asyncio.sleep(wait_time)
            self._tokens = 0.0
            return wait_time
```

#### 13.5.4 熔断器 (Circuit Breaker)

```python
class CircuitState(Enum):
    CLOSED = "closed"       # 正常状态,请求正常通过
    OPEN = "open"           # 熔断状态,快速失败
    HALF_OPEN = "half_open" # 半开状态,允许探测性请求


class CircuitBreaker:
    """
    熔断器 - 保护外部API调用

    三状态流转:
      CLOSED ──连续N次失败──▶ OPEN
       ↑                       │
       │    过了recovery_timeout│ 允许一次探测请求
       │◀──────────────────────┘
       │  探测成功: 回到CLOSED
       │  探测失败: 保持OPEN
       │
       └── 半开状态下允许一个请求通过测试
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,        # 连续多少次失败后打开
        recovery_timeout: float = 30.0,     # 打开后多久尝试半开(秒)
        half_open_max_calls: int = 1,       # 半开状态允许的探测次数
        success_threshold: int = 3          # 半开状态多少次成功才关闭
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs):
        """
        通过熔断器调用受保护的函数

        Raises:
            CircuitOpenError: 熔断器打开时的快速失败
        """
        state = await self._get_state()

        if state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open. "
                f"Fails fast without calling the actual function."
            )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _get_state(self) -> CircuitState:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
            return self._state

    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls += 1
                if self._success_count >= self.success_threshold:
                    # 半开状态下足够多的成功,关闭熔断器
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # 成功则重置失败计数

    async def _on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # 半开状态下失败,重新打开
                self._state = CircuitState.OPEN
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN

    @property
    def state(self) -> CircuitState:
        return self._state
```

#### 13.5.5 降级策略 (Degradation)

```yaml
degradation:
  enabled: true
  
  # 降级链: 按顺序尝试,全部失败则标记为需要人工介入
  chain:
    - provider: "tencent_cloud"        # 主力: 腾讯云(准确率最高)
    - provider: "insight_face_local"   # 降级1: 本地模型(离线兜底)
  
  # 触发条件 (任一满足即触发降级)
  triggers:
    circuit_breaker_open: true          # 熔断器打开时
    quota_remaining_below: 50           # 剩余配额低于50次
    api_latency_above_ms: 3000          # API延迟超过3秒
    consecutive_errors: 10              # 连续10次错误
  
  # 降级后的行为调整
  fallback_config:
    lower_confidence_threshold: true     # 降低置信度阈值(避免过度漏检)
    log_fallback_events: true           # 记录所有降级事件
    notify_on_degradation: true          # 降级时发送通知
```

```python
class DegradationManager:
    """降级管理器 - 在主Provider不可用时自动切换"""

    def __init__(self, facade: FaceRecognizerFacade, config: Dict, event_bus: EventBus):
        self._facade = facade
        self._config = config
        self._bus = event_bus
        self._current_chain_index = 0
        self._is_degraded = False

        # 为每个Provider创建独立的熔断器
        self._breakers: Dict[str, CircuitBreaker] = {}
        for provider in config["chain"]:
            self._breakers[provider["provider"]] = CircuitBreaker(
                name=provider["provider"],
                failure_threshold=config.get("failure_threshold", 5)
            )

    async def recognize_with_protection(self, image_path: str) -> RecognitionResult:
        """带保护的人脸识别调用 (集成限流+熔断+降速)"""
        chain = self._config["chain"]
        last_error = None

        for i, provider_cfg in enumerate(chain):
            provider_name = provider_cfg["provider"]
            breaker = self._breakers[provider_name]

            try:
                # 通过熔断器调用
                result = await breaker.call(
                    self._facade.recognize, image_path
                )
                
                # 如果是从降级状态恢复正常
                if self._is_degraded and i > 0:
                    await self._recover_from_degradation(provider_name)
                
                return result

            except CircuitOpenError:
                # 该Provider熔断打开,尝试下一个
                last_error = e
                continue

            except Exception as e:
                last_error = e
                continue

        # 所有Provider都失败了
        raise AllProvidersExhaustedError(
            f"All {len(chain)} providers exhausted. Last error: {last_error}"
        )

    async def _recover_from_degradation(self, recovered_provider: str):
        """从降级状态恢复"""
        self._is_degraded = False
        self._current_chain_index = 0
        await self._bus.publish(SystemHealthChangedEvent(
            ...,
            message=f"主Provider {recovered_provider} 已恢复正常"
        ))
```

---

### 13.6 图片预处理管道 (Preprocessing Pipeline)

#### 13.6.1 需求动机

| 维度 | 说明 |
|------|------|
| **核心痛点** | 手机拍摄原始照片通常 3-10MB,不同人脸识别Provider要求各异,
且手机拍照含 EXIF Orientation 信息,**不处理会导致旋转90°/180°,直接影响识别准确率** |
| **性能收益** | 预处理后体积减少60-80%,API传输时间缩短,配额利用率提升 |
| **质量保障** | 统一的预处理保证无论什么来源的照片都能正确处理 |

#### 13.6.2 预处理管道设计

```python
class ImagePreprocessor:
    """
    统一图片预处理管道
    
    处理步骤 (按顺序):
      1. 格式验证与转换 (HEIC/WebP/BMP → JPEG)
      2. EXIF方向校正 (⭐ 关键! 手机拍照旋转问题)
      3. 尺寸智能缩放 (保持比例,不超过max_size)
      4. 质量压缩 (JPEG quality 85%, 视觉无损但体积大减)
      5. 输出到临时文件
    
    依赖: Pillow (Pillow>=9.0) / imageio (HEIC支持)
    """

    # 各Provider推荐的预处理参数
    PRESET_MAP = {
        "tencent_cloud": {
            "max_size": (1920, 1080),      # 腾讯云建议最大4MB
            "quality": 85,
            "format": "JPEG",
            "min_face_px": 34
        },
        "baidu": {
            "max_size": (2048, 2048),
            "quality": 85,
            "format": "JPEG",
            "min_face_px": 48
        },
        "insight_face_local": {
            "max_size": (640, 640),          # 本地模型输入较小
            "quality": 90,
            "format": "JPEG",
            "min_face_px": 32
        }
    }

    def __init__(self, provider_name: str, temp_dir: str = "data/temp"):
        self._config = self.PRESET_MAP.get(
            provider_name, self.PRESET_MAP["tencent_cloud"]
        )
        self._temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)

    async def preprocess(
        self,
        image_path: str,
        output_filename: Optional[str] = None
    ) -> PreprocessResult:
        """
        执行完整的预处理流水线

        Args:
            image_path: 原始图片路径
            output_filename: 输出文件名(可选,默认自动生成)

        Returns:
            PreprocessResult: 包含处理后路径、尺寸、格式等信息

        Raises:
            ImageTooLargeError: 超过最大尺寸限制
            ImageInvalidError: 文件损坏或格式不支持
        """
        loop = asyncio.get_event_loop()

        # Step 1: 打开图片
        img = await loop.run_in_executor(
            None, lambda: Image.open(image_path)
        )

        original_format = img.format
        original_size = img.size

        # Step 2: EXIF方向校正 (⭐ 最关键步骤!)
        img = self._apply_exif_orientation(img)

        # Step 3: 尺寸缩放 (保持比例)
        img = self._resize_smart(img)

        # Step 4: 格式转换 (确保输出为JPEG)
        img = self._convert_format(img)

        # Step 5: 写入临时文件
        if output_filename is None:
            output_filename = f"pre_{uuid.uuid4().hex[:12]}.jpg"
        output_path = os.path.join(self._temp_dir, output_filename)

        await loop.run_in_executor(
            None, 
            lambda: img.save(output_path, 'JPEG', 
                           quality=self._config["quality"], optimize=True)
        )

        # 收集结果
        file_size = os.path.getsize(output_path)

        return PreprocessResult(
            original_path=image_path,
            processed_path=output_path,
            original_size=original_size,
            processed_size=img.size,
            original_format=original_format or "UNKNOWN",
            output_format="JPEG",
            file_size_bytes=file_size,
            exif_corrected=True
        )

    def _apply_exif_orientation(self, img: Image.Image) -> Image.Image:
        """
        EXIF方向校正
        
        问题背景: 手机拍照时,相机传感器方向与实际拍摄方向不一致,
        但EXIF中记录了正确的Orientation值。如果不应用此值:
        - 竖拍的照片显示为横置(旋转90°)
        - 倒拍的照片上下颠倒(旋转180°)
        - 这会导致人脸检测完全失败!
        """
        exif = img.getexif()
        orientation = exif.get(0x0112)  # Orientation tag

        if orientation is None:
            return img

        # Orientation 值含义:
        # 1 = 正常, 3 = 旋转180°, 6 = 顺时针90°, 8 = 逆时针90°
        rotation_map = {
            3: Image.ROTATE_180,
            6: Image.ROTATE_270,
            8: Image.ROTATE_90
        }

        method = rotation_map.get(orientation)
        if method:
            img = img.transpose(method)
            # 清除已应用的Orientation标记,避免二次旋转
            # (在保存时会移除EXIF,所以不需要显式删除)

        return img

    def _resize_smart(self, img: Image.Image) -> Image.Image:
        """智能缩放: 保持比例,不超过最大尺寸"""
        max_w, max_h = self._config["max_size"]
        w, h = img.size

        if w <= max_w and h <= max_h:
            return img  # 已经够小,不缩放

        ratio = min(max_w / w, max_h / h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        return img

    def _convert_format(self, img: Image.Image) -> Image.Image:
        """格式转换: 确保RGB模式的JPEG输出"""
        if img.mode in ('RGBA', 'P', 'LA'):
            # RGBA/P/LA 模式转为 RGB (白色背景)
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        return img

    def cleanup_temp_file(self, path: str):
        """清理临时文件 (识别完成后应调用)"""
        try:
            os.remove(path)
        except OSError:
            pass


@dataclass
class PreprocessResult:
    original_path: str
    processed_path: str
    original_size: tuple  # (w, h)
    processed_size: tuple
    original_format: str
    output_format: str
    file_size_bytes: int
    exif_corrected: bool
```

---

### 13.7 双阈值 + 人工审核池 (降低漏检率)

#### 13.7.1 需求动机

| 维度 | 说明 |
|------|------|
| **核心风险** | PRD十二、风险表标注: 重要照片被漏检 = 「中概率 / 高影响」 |
| **矛盾点** | 提高阈值 → 准确率高但**漏检率也升高**(重要照片被误判为不包含目标);
降低阈值 → 漏检率降低但**误判率升高**(大量无关照片混入) |
| **解决方案** | 双阈值策略 + 待审核池,兼顾准确率和召回率 |

#### 13.7.2 双阈值策略

```
识别结果置信度
    │
1.0 ┤                    ★ 高置信区 (≥ 0.92)
    │                    │ 自动通过,直接归档
0.92┤━━━━━━━━━━━━━━━━━━━┿━━━━━━━━★ high_confidence_threshold
    │                    │
    │                    ★ 灰色区间 (0.75 ~ 0.92)
    │                    │ 进入待审核池,由人工确认
0.75┤━━━━━━━━━━━━━━━━━━━┿━━━━━━━━★ low_confidence_threshold
    │                    │
    │                    ★ 低置信区 (< 0.75)
    │                    │ 默认丢弃 (或根据no_face_action配置)
0.0 ┤                    │
    └────────────────────┴──────────────────▶
    
    三种结果:
    ┌─────────────┬──────────────┬──────────────┐
    │  自动通过     │  待人工审核    │  自动丢弃     │
    │  (Auto-Accept)│ (Review-Pool)│ (Auto-Reject) │
    │  置信度 ≥ 0.92 │  0.75 ~ 0.92 │  置信度 < 0.75 │
    └─────────────┴──────────────┴──────────────┘
```

#### 13.7.3 配置项

```yaml
recognition:
  # ====== 双阈值策略 ======
  high_confidence_threshold: 0.92    # 高阈值: 自动通过 (降低此值→更多照片自动通过)
  low_confidence_threshold: 0.75     # 低阈值: 进入审核池 (降低此值→更少照片进审核池)
  
  # ====== 人工审核池 ======
  review_mode:
    enabled: true
    review_pool_dir: "data/review_pending/"   # 待审核照片存放目录
    auto_accept_after_hours: 48               # 超过48小时未审核则自动归档(保守策略)
    max_pool_size: 200                        # 审核池最大容量(超出后最早的自动通过)
    notify_on_new_review_item: true            # 有新的待审核照片时通知
    
  # ====== 边缘案例兜底 ======
  no_face_action: "review"                   # 照片中无人脸时的处理
  # 可选值:
  #   "retain"   - 保留 (可能是背影/侧脸/遮挡)
  #   "discard"  - 丢弃 (确定不是目标)
  #   "review"   - 进入审核池 (推荐,最安全)
```

#### 13.7.4 审核池数据结构

```sql
-- 待审核队列表
CREATE TABLE IF NOT EXISTS review_pool (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER NOT NULL REFERENCES photos_record(id),
    photo_id        TEXT NOT NULL,
    local_path      TEXT NOT NULL,             -- 缩略图路径(供预览)
    original_path   TEXT,                      -- 原图路径
    confidence      REAL NOT NULL,             # 识别置信度
    face_count      INTEGER DEFAULT 0,
    reason          TEXT NOT NULL,
    -- 值域: 'low_confidence' | 'no_face' | 'edge_case' | 'ambiguous_match'
    
    status          TEXT NOT NULL DEFAULT 'pending',
    -- pending(待审核) | approved(确认是目标) | rejected(确认不是) | expired(超时自动通过)
    
    reviewed_by     TEXT,                       # 审核人
    reviewed_at     DATETIME,
    review_note     TEXT,                       # 审核备注
    thumbnail_data  BLOB,                       # 缩略图二进制(用于Web展示)
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME,                   # 过期时间
    
    INDEX idx_review_status (status),
    INDEX idx_review_expires (expires_at)
);
```

---

### 13.8 结构化 Metrics 收集与可观测性

#### 13.8.1 需求动机

| 维度 | 说明 |
|------|------|
| **当前不足** | PRD八、8.1节定义了KPI指标,但仅有文字描述,缺少**自动化收集和可视化方案** |
| **核心价值** | 趋势分析(配额消耗趋势/磁盘增长趋势)、异常检测(识别成功率突降告警)、
运营决策(是否需要升级付费套餐) |

#### 13.8.2 Metrics 定义与收集

```python
class MetricsCollector:
    """
    应用指标收集器 (Prometheus风格)
    
    四种指标类型:
    - Counter: 单调递增计数器 (只增不减)
    - Gauge: 可变数值 (可升可降)
    - Histogram: 分布统计 (分桶计数)
    - Summary: 分位数统计 (p50/p95/p99)
    
    所有指标存储于SQLite,可通过HTTP端点导出供Grafana/Dashboard读取
    """

    # ==================== 计数器 (Counter) ====================

    photos_processed_total = CounterDef(
        name="photos_processed_total",
        help="累计处理照片总数",
        labels=["status"],           # success / failed / skipped / reviewed
    )

    faces_detected_total = CounterDef(
        name="faces_detected_total",
        help="累计检测到的人脸总数",
    )

    target_found_total = CounterDef(
        name="target_found_total",
        help="目标人物命中的照片总数",
        labels=["target_name"],
    )

    api_calls_total = CounterDef(
        name="api_calls_total",
        help="人脸识别API调用总数",
        labels=["provider", "result"],  # success / error / timeout
    )

    tasks_completed_total = CounterDef(
        name="tasks_completed_total",
        help="完成任务总数",
        labels=["trigger_type", "result"],
    )

    # ==================== 仪表盘 (Gauge) ====================

    api_quota_remaining = GaugeDef(
        name="api_quota_remaining",
        help="API剩余配额数",
        labels=["provider"],
    )

    disk_usage_bytes = GaugeDef(
        name="disk_usage_bytes",
        help="照片存储盘使用字节数",
    )

    disk_free_bytes = GaugeDef(
        name="disk_free_bytes",
        help="照片存储盘剩余字节数",
    )

    task_queue_pending = GaugeDef(
        name="task_queue_pending",
        help="待处理任务数量",
    )

    task_queue_failed = GaugeDef(
        name="task_queue_failed",
        help="失败(可重试)的任务数量",
    )

    review_pool_size = GaugeDef(
        name="review_pool_size",
        help="待审核池中的照片数量",
    )

    circuit_breaker_state = GaugeDef(
        name="circuit_breaker_state",
        help="熔断器状态 (0=closed, 1=open, 2=half_open)",
        labels=["provider"],
    )

    # ==================== 直方图 (Histogram) ====================

    recognize_latency_sec = HistogramDef(
        name="recognize_latency_sec",
        help="人脸识别耗时分布(秒)",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
    )

    download_latency_sec = HistogramDef(
        name="download_latency_sec",
        help="照片下载耗时分布(秒)",
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    )

    full_pipeline_latency_sec = HistogramDef(
        name="full_pipeline_latency_sec",
        help="全流程(下载+识别+存储)耗时分布(秒)",
        buckets=[1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
    )

    photo_size_kb = HistogramDef(
        name="photo_size_kb",
        help="照片文件大小分布(KB)",
        buckets=[100, 500, 1000, 2000, 5000, 10000],
    )

    confidence_distribution = HistogramDef(
        name="confidence_distribution",
        help="识别置信度分布",
        buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.93, 0.96, 0.98, 1.0],
    )


class MetricsDB:
    """Metrics 持久化存储 (SQLite + 内存缓存)"""

    def __init__(self, db_path: str):
        self._db = db_path
        self._memory_cache: Dict[str, Any] = {}   # 最新值的内存缓存
        self._init_tables()

    def _init_tables(self):
        """创建metrics相关的表"""
        # metrics_counter 表: 存储Counter类型的累计值
        # metrics_gauge 表: 存储Gauge类型的最新值 + 时间序列
        # metrics_histogram 表: 存储Histogram的桶计数值

    def inc_counter(self, name: str, value: float = 1.0, labels: Dict = None):
        """递增计数器"""
        ...

    def set_gauge(self, name: str, value: float, labels: Dict = None):
        """设置仪表盘值"""
        ...

    def observe_histogram(self, name: str, value: float, labels: Dict = None):
        """记录直方图观察值(自动分配到对应桶)"""
        ...

    def export_prometheus_format(self) -> str:
        """导出为 Prometheus Text Format (供Grafana/其他工具抓取)"""
        ...

    def query_range(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        interval_seconds: int = 3600
    ) -> List[Dict]:
        """查询一段时间内的指标值(用于Dashboard渲染)"""
        ...
```

#### 13.8.3 请求链路追踪 (Trace ID)

```python
class TraceContext:
    """
    请求链路追踪上下文
    
    用途:
    - 每次任务执行分配唯一 TraceID,贯穿所有日志和事件
    - 便于排查问题时串联完整调用链
    - 格式: {YYYYMMDD-HHmmss}-{随机8位hex}
    示例: 20260416-183005-a3b7c2f1
    """

    _context_var: contextvar[Optional[str]] = contextvar("trace_id")

    @classmethod
    def new_trace(cls) -> str:
        """开始一个新的追踪链路"""
        trace_id = (
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{secrets.token_hex(4)}"
        )
        cls._context_var.set(trace_id)
        return trace_id

    @classmethod
    def get_trace_id(cls) -> str:
        """获取当前追踪ID (无则返回占位符)"""
        return cls._context_var.get("no-trace")

    @classmethod
    def set_trace_id(cls, trace_id: str):
        """设置追踪ID (用于子线程/异步任务传递)"""
        cls._context_var.set(trace_id)


# 日志中自动携带 TraceID 的 Filter
class TraceIdLogFilter(logging.Filter):
    """自动将 TraceID 注入每条日志"""

    def filter(self, record: logging.LogRecord):
        record.trace_id = TraceContext.get_trace_id()
        return True

# 日志格式中使用
log_format = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level:<7} | "
    "[{module}] | "
    "[trace:{trace_id}] | "    # <-- 这里!
    "{message}"
)
```

#### 13.8.4 自检健康检查端点 (完善原有API预留)

```yaml
GET /api/v1/health
Response (增强版):
{
  "status": "healthy",              # healthy / degraded / unhealthy
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "last_task_time": "2026-04-16T18:30:05",
  
  "checks": {
    "database": {
      "status": "ok",
      "latency_ms": 2,
      "table_counts": {
        "photos_record": 15234,
        "task_queue": 12,
        "dead_letter_queue": 0,
        "review_pool": 3
      }
    },
    "storage_disk": {
      "status": "ok",
      "total_gb": 500.0,
      "used_gb": 85.3,
      "free_gb": 414.7,
      "utilization_percent": 17.1,
      "warning": false
    },
    "qq_crawler": {
      "status": "ok",
      "crawler_type": "cookie_sim",
      "cookie_expires_in_days": 27,
      "cookie_warning": false
    },
    "face_recognizer": {
      "status": "ok",
      "provider": "tencent_cloud",
      "circuit_breaker": "closed",          # 新增: 熔断器状态
      "quota_remaining": 856,
      "quota_utilization_percent": 14.4,
      "avg_latency_ms": 156,
      "is_degraded": false                  # 新增: 是否处于降级状态
    },
    "task_queue": {
      "status": "ok",
      "pending": 0,
      "processing": 1,
      "failed_retryable": 2,
      "dlq_count": 0
    },
    "event_bus": {
      "status": "ok",
      "subscriber_count": 5,
      "recent_events_per_min": 12
    },
    "review_pool": {
      "status": "warning",                   # 有待审核项目
      "pending_review_count": 3,
      "oldest_age_hours": 18
    }
  },

  "metrics_snapshot": {                     # 新增: 关键指标快照
    "photos_today": 45,
    "targets_found_today": 12,
    "avg_confidence_today": 0.94,
    "api_calls_today": 52,
    "errors_today": 1
  }
}
```

---

### 13.9 安全增强

#### 13.9.1 敏感配置加密存储

```python
from cryptography.fernet import Fernet
from pathlib import Path


class SecureConfig:
    """
    加密配置管理器
    
    保护对象:
    - QQ Cookie 文件 (明文存储有被盗号风险)
    - API SecretKey / 密钥 (虽已通过环境变量,但本地缓存也需要加密)
    
    加密方案:
    - AES-256-GCM (通过 Fernet 对称加密实现)
    - Master Key 首次启动时自动生成,存储于 data/.master_key
    - Windows 下可进一步利用 DPAPI 保护 master key
    """

    MASTER_KEY_FILE = "data/.master_key"

    def __init__(self, workspace_root: str):
        self._workspace = Path(workspace_root)
        self._key_path = self._workspace / self.MASTER_KEY_FILE
        self._fernet = self._load_or_create_key()

    def _load_or_create_key(self) -> Fernet:
        """加载已有的master key,或创建新的"""
        if self._key_path.exists():
            key = self._key_path.read_bytes()
            return Fernet(key)
        else:
            key = Fernet.generate_key()
            self._key_path.parent.mkdir(parents=True, exist_ok=True)
            self._key_path.write_bytes(key)
            # 设置文件权限: 仅当前用户可读
            os.chmod(str(self._key_path), 0o600)
            print(f"[安全提示] 已生成加密密钥文件: {self._key_path}")
            print(f"[安全提示] 请妥善保管此文件,丢失后将无法解密已加密的数据!")
            return Fernet(key)

    def encrypt_value(self, plain_text: str) -> str:
        """加密敏感值为字符串 (可存入YAML/数据库)"""
        encrypted = self._fernet.encrypt(plain_text.encode('utf-8'))
        # 返回 base64 编码的字符串,以 ENC! 前缀标识
        return "ENC!" + encrypted.decode('ascii')

    def decrypt_value(self, encrypted_text: str) -> str:
        """解密 ENC! 前缀的加密值"""
        if not encrypted_text.startswith("ENC!"):
            return encrypted_text  # 未加密的原样返回
        token = encrypted_text[4:].encode('ascii')
        decrypted = self._fernet.decrypt(token)
        return decrypted.decode('utf-8')

    def encrypt_file(self, input_path: str, output_path: str = None):
        """加密整个文件 (如 Cookie 文件)"""
        data = Path(input_path).read_bytes()
        encrypted = self._fernet.encrypt(data)
        out_path = output_path or (input_path + ".enc")
        Path(out_path).write_bytes(encrypted)
        # 删除原文件
        Path(input_path).unlink(missing_ok=True)
        return out_path

    def decrypt_file(self, encrypted_path: str, output_path: str = None):
        """解密整个文件"""
        encrypted = Path(encrypted_path).read_bytes()
        decrypted = self._fernet.decrypt(encrypted)
        out_path = output_path or encrypted_path[:-4]  # 去掉 .enc 后缀
        Path(out_path).write_bytes(decrypted)
        return out_path
```

#### 13.9.2 操作审计日志

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    actor           TEXT NOT NULL DEFAULT 'system',
    -- 'system'(自动操作) / 'user'(用户通过Web/API操作) / 'api'(外部API调用)
    
    action          TEXT NOT NULL,
    -- 动作分类:
    # 采集类: 'login', 'logout', 'fetch_album', 'download_photo'
    # 识别类: 'recognize', 'add_reference', 'remove_target'
    # 存储类: 'store_photo', 'delete_photo', 'organize'
    # 上传类: 'upload_photo', 'create_album'
    # 审核类: 'approve_review', 'reject_review'
    # 配置类: 'config_change', 'switch_provider', 'update_reference'
    # 系统类: 'startup', 'shutdown', 'degrade', 'recover', 'cleanup'
    
    resource_type   TEXT,                    # 'photo' | 'album' | 'target' | 'config' | 'system'
    resource_id     TEXT,                    # 资源标识 (photo_id / album_id 等)
    detail          TEXT,                     # JSON格式的详细信息
    
    ip_address      TEXT,                    # 如通过API调用则记录来源IP
    user_agent      TEXT,                    # 客户端信息
    trace_id        TEXT,                    # 关联的追踪ID
    result          TEXT DEFAULT 'success',   # 'success' | 'failure' | 'denied'
    error_message   TEXT,                    # 失败原因
    
    INDEX idx_audit_timestamp (timestamp),
    INDEX idx_audit_action (action),
    INDEX idx_audit_actor (actor)
);
```

#### 13.9.3 安全配置项补充

```yaml
security:
  # ====== 敏感信息加密 ======
  encryption:
    enabled: true
    master_key_file: "data/.master_key"
    encrypt_cookies: true                  # 加密Cookie文件
    encrypt_api_keys: true                 # 加密本地缓存的API密钥
  
  # ====== 访问控制 ======
  access_control:
    api_auth_enabled: true                 # API是否需要认证 (V2.0启用)
    api_token: "${API_AUTH_TOKEN}"         # API访问令牌
    allowed_ip_ranges:                     # IP白名单 (空则不限)
      - "127.0.0.1/32"
      - "192.168.0.0/16"
    web_ui_password: ""                    # Web界面密码 (空则不需密码,仅本机访问)
    
  # ====== 审计 ======
  audit:
    enabled: true
    retain_days: 180                        # 审计日志保留天数
    log_sensitive_actions: true             # 记录敏感操作(配置变更/删除/登录)
    
  # ====== 数据清理 ======
  data_retention:
    temp_files_max_age_hours: 24           # 临时文件最长保留时间
    error_logs_max_age_days: 30            # 错误日志保留天数
    auto_cleanup_enabled: true             # 是否启用自动清理
    cleanup_schedule: "0 4 * * *"          # 凌晨4点执行清理
```

---

### 13.10 部署优化

#### 13.10.1 Docker 化部署

```dockerfile
# ==================== Dockerfile ====================
FROM python:3.10-slim

LABEL maintainer="BabyPhotos Tool"
LABEL version="1.0"
LABEL description="宝宝照片自动筛选工具"

# 设置工作目录
WORKDIR /app

# 安装系统依赖 (图像处理需要的库)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装Python包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录结构 (挂载卷)
RUN mkdir -p /data/photos /data/config /data/logs /data/db /data/models /data/temp

# 暴露Web管理界面端口 (V2.0)
EXPOSE 8080

# 数据卷声明
VOLUME ["/data/photos", "/data/config", "/data/logs", "/data/db"]

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 健康检查
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "from app.health import check; check()" || exit 1

# 启动命令
CMD ["python", "main.py"]
```

```yaml
# ==================== docker-compose.yml ====================
version: '3.8'

services:
  baby-photos:
    build: .
    container_name: baby-photos
    restart: unless-stopped
    ports:
      - "8080:8080"          # Web管理界面 (V2.0)
    volumes:
      - ./data/photos:/data/photos:rw        # 照片存储 (绑定挂载,方便查看)
      - ./data/config:/data/config:ro        # 配置文件 (只读容器内)
      - ./data/logs:/data/logs:rw            # 日志
      - ./data/db:/data/db:rw                # SQLite数据库
      - ./data/models:/data/models:rw        # AI模型文件
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
      # 敏感信息从 .env 注入 (不写进 compose)
      - TENCENT_SECRET_ID=${TENCENT_SECRET_ID}
      - TENCENT_SECRET_KEY=${TENCENT_SECRET_KEY}
      - BAIDU_API_KEY=${BAIDU_API_KEY}
      - BAIDU_SECRET_KEY=${BAIDU_SECRET_KEY}
    # 资源限制
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"

# 可选: Grafana 监控面板 (Phase 4+)
  grafana:
    image: grafana/grafana:latest
    container_name: baby-photos-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on:
      - baby-photos

volumes:
  grafana-data:
```

#### 13.10.2 配置向导 (首次运行体验)

对于技术水平普通的家长用户,首次配置体验至关重要:

```bash
$ python main.py --setup

╔══════════════════════════════════════════════════════════╗
║                                                          ║
║     🎒 宝宝照片管家 - 初始化配置向导                      ║
║                                                          ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  第 1/7 步: 请输入班级QQ群号                               ║
║  ════════════════════════════════════                    ║
║  > 123456789                                              ║
║                                                          ║
║  第 2/7 步: 选择照片存储位置                                ║
║  ════════════════════════════════════                    ║
║  默认: D:\BabyPhotos                                      ║
║  > (直接回车使用默认 / 输入自定义路径)                       ║
║                                                          ║
║  第 3/7 步: 选择人脸识别引擎                               ║
║  ════════════════════════════════════                    ║
║                                                            ║
║    [1] 腾讯云人脸识别 (推荐, 准确率99%+, 1000次/月免费)    ║
║    [2] 百度AI人脸识别 (免费额度大, QPS限制内免费)           ║
║    [3] 本地InsightFace (完全离线, 无需网络, 无限免费)       ║
║                                                            ║
║  > 1                                                       ║
║                                                            ║
║  第 4/7 步: 腾讯云API密钥配置                               ║
║  ════════════════════════════════════                    ║
║  Secret ID: > AKIDxxxxxxxxxxxxxx                          ║
║  Secret Key: > (输入后隐藏)                                 ║
║  地域: ap-guangzhou (默认)                                  ║
║                                                            ║
║  第 5/7 步: 导入宝宝参考照片                                ║
║  ════════════════════════════════════                    ║
║  请将宝宝的清晰正面照放入以下目录后回车:                      ║
║  config/reference_photos/daughter/                         ║
║  (建议10-20张不同角度/表情的照片)                             ║
║  已检测到 12 张照片 ✓                                       ║
║                                                            ║
║  第 6/7 步: 是否开启企业微信通知?                            ║
║  ════════════════════════════════════                    ║
║  > y                                                       ║
║  Webhook URL: > https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
║                                                            ║
║  第 7/7 步: 定时任务配置                                    ║
║  ════════════════════════════════════                    ║
║  执行频率: 每30分钟 (默认, 适配放学后时间段)                   ║
║  启动时回溯扫描: 最近7天 (默认)                              ║
║                                                            ║
║  ═══════════════════════════════════════════════════════════║
║                                                            ║
║  ✅ 配置完成!                                              ║
║                                                            ║
║  配置文件: config/config.yaml                               ║
║  参考照片: 12 张 (宝贝女儿)                                 ║
║  存储路径: D:\BabyPhotos                                   ║
║  通知渠道: 企业微信 ✓                                       ║
║                                                            ║
║  接下来您可以:                                               ║
║    • 运行 python main.py --test 进行首次测试                 ║
║    • 运行 python main.py --run 立即执行一次完整流程          ║
║    • 运行 python main.py          启动后台常驻服务            ║
║                                                            ║
╚══════════════════════════════════════════════════════════╝
```

---

### 13.11 优化项总览与优先级排序

| 优先级 | 优化项 | 所属领域 | 投入产出比 | 依赖关系 |
|--------|--------|---------|-----------|---------|
| **P0** | 事件总线 (EventBus) | 架构解耦 | ★★★★★ | 无,可立即实施 |
| **P0** | 采集器可插拔架构 | 风险防御 | ★★★★★ | 无,对标人脸识别 |
| **P0** | 图片预处理管道 (EXIF校正) | 准确率保障 | ★★★★★ | 无,直接影响识别效果 |
| **P1** | 任务队列持久化 + 状态机 | 可靠性 | ★★★★☆ | 依赖 EventBus |
| **P1** | 熔断器 + 限流 + 降级 | 故障防护 | ★★★★☆ | 依赖任务队列 |
| **P1** | 识别结果缓存层 | 性能/成本 | ★★★☆☆ | 依赖任务队列 |
| **P2** | 结构化 Metrics + 健康检查 | 可观测性 | ★★★☆☆ | 依赖基础框架 |
| **P2** | 双阈值 + 人工审核池 | 质量/召回率 | ★★★☆☆ | 依赖识别框架 |
| **P2** | 存储后端可插拔 | 扩展性 | ★★☆☆☆ | 依赖存储管理器重构 |
| **P3** | 配置向导 + Docker化 | 用户体验 | ★★☆☆☆ | 无,可独立实施 |
| **P3** | 安全增强 (加密/审计) | 安全合规 | ★★☆☆☆ | 无,可逐步引入 |

**推荐迭代路线:**
```
Phase 1 (Week 1-2): P0 全部 → 事件总线 + 采集器可插拔 + 图片预处理
Phase 2 (Week 3-4): P1 全部 → 任务队列 + 熔断降级 + 结果缓存
Phase 3 (Week 5-6): P2 核心 → Metrics + 双阈值审核池
Phase 4 (Week 7-8): P2/P3 → 存储后端 + Docker化 + 配置向导
Phase 5 (Week 9+): P3 完善 → 安全增强 + Grafana Dashboard
```
