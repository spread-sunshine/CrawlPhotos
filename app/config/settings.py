# -*- coding: utf-8 -*-
"""
Configuration settings management module.
配置管理模块 - YAML加载、环境变量替换、统一配置访问.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Default config file path (relative to project root)
# __file__: app/config/settings.py -> parent.parent.parent = project root
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"

# Environment variable pattern: ${VAR_NAME} or ${VAR_NAME:default}
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


class ConfigError(Exception):
    """Configuration related error."""
    pass


class Settings:
    """
    Application settings manager.

    Responsibilities:
    - Load YAML configuration file with environment variable substitution.
    - Provide unified access to all configuration sections.
    - Support nested key access via dot notation.

    Usage:
        settings = Settings.load()
        qq_group_id = settings.get("qq.group.group_id")
        provider = settings.get("face_recognition.provider")
    """

    def __init__(self, config_dict: Dict[str, Any]):
        self._config: Dict[str, Any] = config_dict

    @classmethod
    def load(
        cls,
        config_path: Optional[Path] = None,
    ) -> "Settings":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config YAML file.
                          Defaults to config/config.yaml.

        Returns:
            Settings instance.

        Raises:
            ConfigError: When config file not found or invalid.
        """
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH

        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        if raw_config is None:
            raw_config = {}

        # Recursively resolve environment variables
        resolved = cls._resolve_env_vars(raw_config)
        return cls(resolved)

    @staticmethod
    def _resolve_env_vars(obj: Any) -> Any:
        """
        Recursively replace ${VAR} and ${VAR:default} patterns
        with environment variable values.
        """
        if isinstance(obj, str):
            def _replacer(match):
                var_name = match.group(1)
                default_val = match.group(2)
                env_val = os.getenv(var_name)
                if env_val is not None:
                    return env_val
                if default_val is not None:
                    return default_val
                return match.group(0)  # Keep original if not found

            return _ENV_VAR_PATTERN.sub(_replacer, obj)

        elif isinstance(obj, dict):
            return {k: Settings._resolve_env_vars(v)
                    for k, v in obj.items()}

        elif isinstance(obj, list):
            return [Settings._resolve_env_vars(item) for item in obj]

        return obj

    def get(
        self,
        key_path: str,
        default: Any = None,
    ) -> Any:
        """
        Get configuration value by dotted key path.

        Args:
            key_path: Dot-separated path, e.g. 'qq.group.group_id'.
            default: Default value when key not found.

        Returns:
            Configuration value or default.
        """
        keys = key_path.split(".")
        current: Any = self._config
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current

    def get_section(self, section_name: str) -> Dict[str, Any]:
        """
        Get an entire configuration section as a dictionary.

        Args:
            section_name: Top-level section name.

        Returns:
            Section dictionary or empty dict if not found.
        """
        return self._config.get(section_name, {})

    def require(self, key_path: str) -> Any:
        """
        Get required configuration value; raise if missing.

        Args:
            key_path: Dot-separated path.

        Returns:
            Configuration value.

        Raises:
            ConfigError: When the required key is missing.
        """
        value = self.get(key_path)
        if value is None or value == "":
            raise ConfigError(
                f"Required config key is missing or empty: '{key_path}'"
            )
        return value

    @property
    def raw(self) -> Dict[str, Any]:
        """Return the raw configuration dictionary."""
        return self._config

    def __repr__(self) -> str:
        sections = list(self._config.keys())
        return f"Settings(sections={sections})"
