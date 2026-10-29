"""Configuration with safe defaults; can be overridden by a JSON file and CLI flags."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Dict


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    db_path: str = "out/sessions.db"
    report_dir: str = "out/reports"
    gap_minutes: float = 30.0
    # Maps source column names to canonical names, e.g. {"ts": "event_time", "uid": "user_id"}.
    column_map: Dict[str, str] = field(default_factory=dict)
    # Fail (and roll back) the run if more than this share of input rows is rejected. 1.0 = never fail.
    max_reject_rate: float = 1.0

    @property
    def gap_seconds(self) -> int:
        return int(round(self.gap_minutes * 60))

    def validate(self) -> "Config":
        if not isinstance(self.gap_minutes, (int, float)) or self.gap_minutes <= 0:
            raise ConfigError("gap_minutes must be a positive number")
        if self.gap_seconds < 1:
            raise ConfigError("gap_minutes is too small (must be at least 1 second)")
        if not 0.0 <= self.max_reject_rate <= 1.0:
            raise ConfigError("max_reject_rate must be between 0 and 1")
        if not isinstance(self.column_map, dict):
            raise ConfigError("column_map must be an object of {source_name: canonical_name}")
        return self


def load_config(path: str) -> Config:
    """Load settings from a JSON file. Unknown keys are an error (catches typos)."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file is not valid JSON: {exc}")
    if not isinstance(raw, dict):
        raise ConfigError("config file must contain a JSON object")
    allowed = {f.name for f in fields(Config)}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"unknown config keys: {unknown}; allowed: {sorted(allowed)}")
    return Config(**raw).validate()
