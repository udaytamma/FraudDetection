"""
Model Registry

Persists model metadata for champion/challenger routing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ModelEntry:
    name: str
    version: str
    path: str
    framework: str
    model_type: str
    trained_at: str
    auc: Optional[float] = None
    feature_columns: Optional[list[str]] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "framework": self.framework,
            "model_type": self.model_type,
            "trained_at": self.trained_at,
            "auc": self.auc,
            "feature_columns": self.feature_columns,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }

    @staticmethod
    def from_dict(data: dict) -> "ModelEntry":
        return ModelEntry(
            name=data.get("name") or "unknown",
            version=data.get("version") or "unknown",
            path=data.get("path") or "",
            framework=data.get("framework") or "",
            model_type=data.get("model_type") or "",
            trained_at=data.get("trained_at") or "",
            auc=data.get("auc"),
            feature_columns=data.get("feature_columns"),
            window_start=data.get("window_start"),
            window_end=data.get("window_end"),
        )


class ModelRegistry:
    """Loads and persists model registry metadata."""

    def __init__(self, registry_path: str):
        self.path = Path(registry_path)
        self.data: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.data = {}
            return
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get(self, slot: str) -> Optional[ModelEntry]:
        entry = self.data.get(slot)
        if not entry:
            return None
        return ModelEntry.from_dict(entry)

    def set(self, slot: str, entry: ModelEntry) -> None:
        self.data[slot] = entry.to_dict()
        self.save()

    def ensure_default(self, champion: Optional[ModelEntry] = None) -> None:
        if self.data:
            return
        if champion:
            self.set("champion", champion)
            return
        self.data = {}
        self.save()

