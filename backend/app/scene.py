"""F5 bridge: build a GLB from a layout with the deterministic scene builder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SCENE_PATH = ROOT / "scripts" / "build_scene.py"

_lock = threading.Lock()
_module = None
_cache: dict[str, bytes] = {}


def _builder():
    global _module
    if _module is None:
        spec = importlib.util.spec_from_file_location("plan2walk_scene_builder", _SCENE_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load scene builder at {_SCENE_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module = module
    return _module


def build_glb(plan: dict) -> bytes:
    key = hashlib.sha1(json.dumps(plan, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    with _lock:
        if key in _cache:
            return _cache[key]
    builder = _builder()
    plan_width = 1.0 if plan.get("units") == "m" else float(plan.get("plan_width_m") or 15.0)
    scene = builder.build(
        plan,
        plan_width=plan_width,
        wall_height=float(plan.get("wall_height") or 2.7),
        floor_thickness=0.05,
        ceilings=True,
        windows=True,
    )
    data = scene.export(file_type="glb")
    if not isinstance(data, (bytes, bytearray)):
        raise RuntimeError("scene export did not return bytes")
    with _lock:
        if len(_cache) > 24:
            _cache.clear()
        _cache[key] = bytes(data)
    return bytes(data)
