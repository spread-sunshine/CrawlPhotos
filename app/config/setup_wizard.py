# -*- coding: utf-8 -*-
"""
Configuration Setup Wizard.
配置向导 - 引导用户首次运行时完成初始化设置.

Usage:
    python main.py --setup

Steps:
    1. QQ Group ID
    2. Storage path
    3. Face recognition engine selection
    4. API credentials (if cloud provider)
    5. Reference photos import
    6. Notification settings
    7. Scheduler configuration
"""

import os
import shutil
import sys
from pathlib import Path

from app.config.logging_config import get_logger

logger = get_logger(__name__)

# Default config template
_DEFAULT_CONFIG = """# 宝宝照片管家 - 配置文件 (由向导自动生成)
# Baby Photos Auto-Filter Tool Configuration

qq:
  group:
    group_id: "{group_id}"
    album_id: ""
    cookies_file: "data/qq_cookies.txt"
  personal:
    auto_upload: false

face_recognition:
  provider: "{provider}"
  {provider_config}

  targets:
    - name: "{target_name}"
      reference_photos_dir: "config/reference_photos/{target_dir}/"
      min_confidence: 0.80
      enabled: true

recognition:
  high_confidence_threshold: 0.92
  low_confidence_threshold: 0.75
  review_mode:
    enabled: true
    review_pool_dir: "data/review_pending/"
    auto_accept_after_hours: 48
    max_pool_size: 200
  no_face_action: "review"

storage:
  root_directory: "{storage_path}"
  filename_format: "{{year}}/{{month_date}}/{{YYYYMMDD}}_{{seq}}_{{source}}.jpg"

scheduler:
  cron_expression: "0 */30 * * * *"
  startup_scan: true
  scan_days_back: 7

logging:
  level: INFO
  directory: logs
  max_size_mb: 50
  retention_days: 90

notification:
  enabled: {notify_enabled}
  wechat_work:
    webhook_url: ""
    daily_report_time: "21:00"

api:
  enabled: true
  host: "127.0.0.1"
  port: 8080
"""


class SetupWizard:
    """
    Interactive CLI wizard for first-time setup.
    
    Guides user through 7 steps to generate config.yaml.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self._config_path = Path(config_path)
        self._answers = {}

    def run(self) -> bool:
        """Execute the full setup wizard."""
        self._print_banner()

        try:
            self.step_qq_group()
            self.step_storage()
            self.step_recognition_engine()
            self.step_api_credentials()
            self.step_reference_photos()
            self.step_notification()
            self.step_scheduler()
            self.write_config()
            self.print_summary()
            return True
        except KeyboardInterrupt:
            print("\n\n已取消配置向导。")
            return False

    def _print_banner(self):
        width = 60
        print("\n" + "=" * width)
        print("   🎒  宝宝照片管家 - 初始化配置向导")
        print("=" * width + "\n")

    def _input(self, prompt: str, default: str = "") -> str:
        default_str = f" [{default}]" if default else ""
        value = input(f"  > {prompt}{default_str}: ").strip()
        if not value and default:
            return default
        return value

    def _input_bool(self, prompt: str, default: bool = False) -> bool:
        hint = "Y/n" if default else "y/N"
        raw = input(f"  > {prompt} ({hint}): ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes", "是", "1", "true")

    # ---- Steps ----

    def step_qq_group(self):
        print("  第 1/7 步: 请输入班级QQ群号")
        print("  " + "-" * 40)

        group_id = self._input("群号")
        while not group_id or not group_id.isdigit():
            print("  [!] 群号必须为数字")
            group_id = self._input("群号")

        self._answers["group_id"] = group_id
        print()

    def step_storage(self):
        print("  第 2/7 步: 选择照片存储位置")
        print("  " + "-" * 40)

        default_storage = str(Path.home() / "BabyPhotos")
        storage = self._input(
            "存储路径",
            default=default_storage,
        )
        self._answers["storage_path"] = storage
        print()

    def step_recognition_engine(self):
        print("  第 3/7 步: 选择人脸识别引擎")
        print("  " + "-" * 40)
        print("    [1] 腾讯云人脸识别 "
              "(推荐, 准确率高, 1000次/月免费)")
        print("    [2] 百度AI人脸识别 "
              "(免费额度大)")
        print("    [3] InsightFace本地模型 "
              "(完全离线, 无需网络)")

        choice = self._input("选择", default="1")

        if choice == "1":
            self._answers["provider"] = "tencent_cloud"
            self._answers[
                "provider_config"
            ] = (
                'tencent_cloud:\n'
                '    secret_id: ""\n'
                '    secret_key: ""\n'
                '    region: "ap-guangzhou"'
            )
        elif choice == "2":
            self._answers["provider"] = "baidu"
            self._answers[
                "provider_config"
            ] = (
                'baidu:\n'
                '    app_id: ""\n'
                '    api_key: ""\n'
                '    secret_key: ""'
            )
        elif choice == "3":
            self._answers["provider"] = "insightface"
            self._answers[
                "provider_config"
            ] = (
                'insightface:\n'
                '    model_name: "buffalo_l"\n'
                '    use_gpu: false'
            )
        else:
            self._answers["provider"] = "tencent_cloud"
            self._answers[
                "provider_config"
            ] = (
                'tencent_cloud:\n'
                '    secret_id: ""\n'
                '    secret_key: ""\n'
                '    region: "ap-guangzhou"'
            )

        self._answers["target_name"] = "宝贝女儿"
        self._answers["target_dir"] = "daughter"
        print()

    def step_api_credentials(self):
        if self._answers.get("provider") in ("tencent_cloud", "baidu"):
            print(f"  第 4/7 步: "
                  f"{self._answers['provider']} API密钥配置")
        else:
            return

        print("  " + "-" * 40)

        if self._answers["provider"] == "tencent_cloud":
            sid = self._input("Secret ID")
            sk = self._input("Secret Key")
            region = self._input("地域", default="ap-guangzhou")
            self._answers["provider_config"] = (
                f'tencent_cloud:\n'
                f'    secret_id: "{sid}"\n'
                f'    secret_key: "{sk}"\n'
                f'    region: "{region}"'
            )
        elif self._answers["provider"] == "baidu":
            aid = self._input("App ID")
            ak = self._input("API Key")
            bsk = self._input("Secret Key")
            self._answers["provider_config"] = (
                f'baidu:\n'
                f'    app_id: "{aid}"\n'
                f'    api_key: "{ak}"\n'
                f'    secret_key: "{bsk}"'
            )

        print()

    def step_reference_photos(self):
        print("  第 5/7 步: 导入宝宝参考照片")
        print("  " + "-" * 40)

        ref_dir = Path("config/reference_photos") / self._answers.get("target_dir", "daughter")
        ref_dir.mkdir(parents=True, exist_ok=True)

        exts = {".jpg", ".jpeg", ".png", ".webp"}
        existing = [
            p for p in ref_dir.iterdir() if p.suffix.lower() in exts
        ]

        if existing:
            print(f'  已检测到 {len(existing)} 张参考照片')
            for p in sorted(existing)[:10]:
                print(f'    - {p.name}')
            if len(existing) > 10:
                print(f'    ... 还有 {len(existing)-10} 张')
        else:
            print(f'  请将宝宝清晰正面照放入以下目录后回车:')
            print(f'  {ref_dir.absolute()}')
            self._input("(按回车继续)")

        print()

    def step_notification(self):
        print("  第 6/7 步: 是否开启企业微信通知?")
        print("  " + "-" * 40)

        notify = self._input_bool("启用通知", default=False)
        self._answers["notify_enabled"] = str(notify).lower()

        if notify:
            webhook = self._input("Webhook URL", default="")
            self._answers["webhook_url"] = webhook
        print()

    def step_scheduler(self):
        print("  第 7/7 步: 定时任务配置")
        print("  " + "-" * 40)

        cron = self._input("执行频率Cron表达式",
                           default="0 */30 * * * *")
        scan_days = self._input("启动回溯天数(天)",
                                 default="7")

        self._answers["cron_expression"] = cron
        self._answers["scan_days_back"] = int(scan_days) if scan_days.isdigit() else 7
        print()

    def write_config(self) -> None:
        """Generate config.yaml from collected answers."""
        self._config_path.parent.mkdir(parents=True,
                                       exist_ok=True)

        config_content = _DEFAULT_CONFIG.format(
            group_id=self._answers.get("group_id", ""),
            provider=self._answers.get("provider", "tencent_cloud"),
            provider_config=self._answers.get(
                "provider_config", ""
            ),
            target_name=self._answers.get("target_name", ""),
            target_dir=self._answers.get("target_dir", ""),
            storage_path=self._answers.get("storage_path",
                                          "./output"),
            notify_enabled=self._answers.get(
                "notify_enabled", "false"
            ),
        )

        with open(self._config_path, "w",
                  encoding="utf-8") as f:
            f.write(config_content)

        logger.info("Config written to %s", self._config_path)

    def print_summary(self) -> None:
        """Print final summary."""
        print("\n" + "=" * 60)
        print("  ✅  配置完成!")
        print("=" * 60)
        print()
        print(f'  配置文件: {self._config_path}')
        print(
            f'  存储路径: '
            f'{self._answers.get("storage_path", "./output")}'
        )
        print(
            f'  识别引擎: '
            f'{self._answers.get("provider", "unknown")}'
        )
        notify_status = (
            "企业微信 ✓"
            if self._answers.get("notify_enabled") == "true"
            else "未启用"
        )
        print(f'  通知渠道: {notify_status}')
        print()
        print('  接下来您可以:')
        print('    • python main.py --test  首次测试')
        print('    • python main.py --run   执行一次完整流程')
        print('    • python main.py         启动后台常驻服务')
        print()


def run_setup_wizard(config_path: str = None) -> None:
    """Entry point for --setup mode."""
    path = config_path or "config/config.yaml"

    if Path(path).exists():
        overwrite = input(
            f"\n  配置文件 {path} 已存在。是否覆盖? (y/N): "
        ).strip().lower()
        if overwrite not in ("y", "yes", "是"):
            print("  已取消。如需重新配置，请先手动删除现有配置文件。")
            return

    wizard = SetupWizard(config_path=path)
    success = wizard.run()

    if success:
        logger.info("Setup wizard completed successfully")
    else:
        logger.warning("Setup wizard was cancelled")


if __name__ == "__main__":
    run_setup_wizard()
