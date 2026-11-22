"""Tiny JSON-file store for generated plans."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .layout import plan_metrics


class PlanStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
        for path in self.directory.glob("*.json"):
            try:
                self._cache[path.stem] = json.loads(path.read_text())
            except Exception:
                continue

    def save(self, plan: dict) -> dict:
        plan_id = plan["plan_id"]
        plan["updated_at"] = time.time()
        with self._lock:
            self._cache[plan_id] = plan
            target = self.directory / f"{plan_id}.json"
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(plan, indent=2))
            os.replace(tmp, target)
        return plan

    def get(self, plan_id: str) -> dict | None:
        return self._cache.get(plan_id)

    def list(self) -> list[dict]:
        items = []
        for plan in self._cache.values():
            items.append(
                {
                    "plan_id": plan.get("plan_id"),
                    "title": plan.get("title") or plan.get("plan_id"),
                    "source": plan.get("source", "unknown"),
                    "updated_at": plan.get("updated_at", 0),
                    "metrics": plan_metrics(plan),
                }
            )
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return items

    def delete(self, plan_id: str) -> bool:
        with self._lock:
            self._cache.pop(plan_id, None)
            target = self.directory / f"{plan_id}.json"
            if target.exists():
                target.unlink()
                return True
        return False
