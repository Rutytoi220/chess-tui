"""Configuration loading, saving, presets, and dot-path mutation."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
import os
from pathlib import Path
import shutil
import tomllib
from typing import Any

from platformdirs import user_config_dir, user_data_dir
import tomli_w

from .schema import (
    BoardConfig,
    BridgeConfig,
    ChessTuiConfig,
    HintConfig,
    InputConfig,
    LayoutConfig,
)


def default_config_dir() -> Path:
    """Return the XDG config directory for chess-tui."""
    override = os.environ.get("CHESS_TUI_CONFIG_DIR")
    return Path(override) if override else Path(user_config_dir("chess-tui"))


def default_data_dir() -> Path:
    """Return the XDG data directory for chess-tui (accounts, browser profiles)."""
    override = os.environ.get("CHESS_TUI_DATA_DIR")
    return Path(override) if override else Path(user_data_dir("chess-tui"))


def _merge_dataclass(instance: Any, raw: dict[str, Any]) -> Any:
    """Recursively update a dataclass instance from a parsed TOML dict."""
    for f in fields(instance):
        if f.name not in raw:
            continue
        val = raw[f.name]
        current = getattr(instance, f.name)
        if is_dataclass(current) and isinstance(val, dict):
            _merge_dataclass(current, val)
        elif isinstance(current, dict) and isinstance(val, dict):
            merged = dict(current)
            merged.update(val)
            setattr(instance, f.name, merged)
        else:
            setattr(instance, f.name, val)
    return instance


def _coerce_value(current: Any, raw_str: str) -> Any:
    """Coerce a CLI / `:set` string value to match the target field type."""
    if isinstance(current, bool):
        low = raw_str.strip().lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"Expected boolean, got {raw_str!r}")
    if isinstance(current, int):
        return int(raw_str)
    if isinstance(current, float):
        return float(raw_str)
    if isinstance(current, list):
        return [item.strip() for item in raw_str.split(",") if item.strip()]
    return raw_str


class ConfigManager:
    """Manages loading, saving, live editing, and named presets for ChessTuiConfig."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_dir = config_path.parent if config_path else default_config_dir()
        self.config_path = config_path or (self.config_dir / "config.toml")
        self.presets_dir = self.config_dir / "presets"
        self.config: ChessTuiConfig = self.load()

    def load(self) -> ChessTuiConfig:
        """Load config from TOML, creating defaults if missing."""
        cfg = ChessTuiConfig(
            hints=HintConfig(),
            board=BoardConfig(),
            layout=LayoutConfig(),
            input=InputConfig(),
            bridge=BridgeConfig(),
        )
        if self.config_path.exists():
            with self.config_path.open("rb") as fh:
                raw = tomllib.load(fh)
            _merge_dataclass(cfg, raw)
        self.config = cfg
        return cfg

    def save(self) -> Path:
        """Persist current config to disk as readable TOML."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = self.config.to_dict()
        # Strip empty custom maps unless populated to keep config tidy, or serialize cleanly
        with self.config_path.open("wb") as fh:
            tomli_w.dump(payload, fh)
        return self.config_path

    def ensure_exists(self) -> Path:
        """Write default config.toml if one does not exist yet."""
        if not self.config_path.exists():
            self.save()
        return self.config_path

    def get_by_path(self, dot_path: str) -> Any:
        """Retrieve a setting via dot path (e.g. 'hints.alphabet' or 'theme')."""
        obj: Any = self.config
        for part in dot_path.split("."):
            if is_dataclass(obj) and hasattr(obj, part):
                obj = getattr(obj, part)
            elif isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                raise KeyError(f"Unknown config key: {dot_path}")
        return obj

    def set_by_path(self, dot_path: str, value: Any, persist: bool = True) -> Any:
        """Update a setting via dot path (supports string coercion from `:set`)."""
        parts = dot_path.split(".")
        obj: Any = self.config
        for part in parts[:-1]:
            if is_dataclass(obj) and hasattr(obj, part):
                obj = getattr(obj, part)
            elif isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                raise KeyError(f"Unknown config section: {dot_path}")

        leaf = parts[-1]
        if is_dataclass(obj) and hasattr(obj, leaf):
            current = getattr(obj, leaf)
            coerced = _coerce_value(current, value) if isinstance(value, str) else value
            setattr(obj, leaf, coerced)
        elif isinstance(obj, dict):
            current = obj.get(leaf, "")
            coerced = _coerce_value(current, value) if isinstance(value, str) else value
            obj[leaf] = coerced
        else:
            raise KeyError(f"Unknown config key: {dot_path}")

        if persist:
            self.save()
        return coerced

    def save_preset(self, name: str) -> Path:
        """Save current configuration as a named preset."""
        safe = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_"))
        if not safe:
            raise ValueError("Preset name must contain alphanumeric characters.")
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        dest = self.presets_dir / f"{safe}.toml"
        with dest.open("wb") as fh:
            tomli_w.dump(self.config.to_dict(), fh)
        return dest

    def load_preset(self, name: str) -> ChessTuiConfig:
        """Load a named preset and apply it as active config."""
        safe = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_"))
        src = self.presets_dir / f"{safe}.toml"
        if not src.exists():
            raise FileNotFoundError(f"Preset {name!r} not found at {src}")
        shutil.copy2(src, self.config_path)
        return self.load()

    def list_presets(self) -> list[str]:
        """List saved preset names."""
        if not self.presets_dir.exists():
            return []
        return sorted(p.stem for p in self.presets_dir.glob("*.toml"))
