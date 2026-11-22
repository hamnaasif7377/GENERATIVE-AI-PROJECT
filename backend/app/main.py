"""Plan2Walk FastAPI app: F1 chat, F2 image import, F3 validation, F4 edits, F5 GLB."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .genai import get_provider
from .layout import normalise_type, room_label, scale_of, wall_length
from .planner import plan_from_prompt
from .scene import build_glb
from .store import PlanStore
from .validator import validate
from .vision import VisionError, plan_from_image

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DATA_DIR = Path(os.getenv("PLAN2WALK_DATA", str(ROOT / "data" / "generated")))

app = FastAPI(title="Plan2Walk", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = PlanStore(DATA_DIR)
app.state.provider = get_provider()
_health_cache: dict = {"at": 0.0, "value": None}


def _provider():
    return app.state.provider


def _health() -> dict:
    now = time.time()
    if _health_cache["value"] is None or now - _health_cache["at"] > 10:
        try:
            value = _provider().health()
        except Exception as exc:  # noqa: BLE001
            value = {"provider": "none", "available": False, "error": str(exc)}
        _health_cache.update({"at": now, "value": value})
    return _health_cache["value"]


def _get_plan(plan_id: str) -> dict:
    plan = store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"plan {plan_id} not found")
    return plan


def _revalidate(plan: dict, repair: bool = False) -> dict:
    report = validate(plan, repair=repair)
    plan["validation"] = report
    store.save(plan)
    return report


def _response(plan: dict, message: str, provider: str, warnings: list[str] | None = None) -> dict:
    return {
        "plan": plan,
        "message": message,
        "provider": provider,
        "warnings": warnings or [],
        "validation": plan.get("validation") or validate(plan),
        "metrics": (plan.get("validation") or {}).get("metrics", {}),
    }


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    seed: int = 0


class RoomPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    type: str | None = None


class OpeningCreate(BaseModel):
    kind: Literal["door", "window"]
    wall: int
    offset: float | None = None
    width: float | None = None
    sill: float | None = None
    height: float | None = None


class OpeningPatch(BaseModel):
    kind: Literal["door", "window"] | None = None
    wall: int | None = None
    offset: float | None = None
    width: float | None = None
    sill: float | None = None
    height: float | None = None


class ValidateRequest(BaseModel):
    repair: bool = False


# ---------------------------------------------------------------------------
# F1 / F2
# ---------------------------------------------------------------------------


@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        result = plan_from_prompt(request.message, provider=_provider(), seed=request.seed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save(result["plan"])
    return _response(result["plan"], result["message"], result["provider"], result["warnings"])


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    width_m: float | None = Form(default=None),
    scale: str | None = Form(default=None),
):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file is larger than 20 MB")
    if not data:
        raise HTTPException(status_code=422, detail="the uploaded file is empty")
    hint = width_m
    if hint is None and scale:
        try:
            hint = float(scale)
        except ValueError:
            hint = None
    try:
        result = plan_from_image(data, file.filename or "", width_m=hint, provider=_provider())
    except VisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save(result["plan"])
    return _response(result["plan"], result["message"], result["provider"], result["warnings"])


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    info = dict(_health())
    info["plans"] = len(store.list())
    return info


@app.get("/api/plans")
def list_plans():
    return {"plans": store.list()}


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    return _get_plan(plan_id)


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: str):
    if not store.delete(plan_id):
        raise HTTPException(status_code=404, detail=f"plan {plan_id} not found")
    return {"deleted": plan_id}


# ---------------------------------------------------------------------------
# F4: manual corrections
# ---------------------------------------------------------------------------


@app.patch("/api/plans/{plan_id}/rooms/{room_id}")
def patch_room(plan_id: str, room_id: int, patch: RoomPatch):
    plan = _get_plan(plan_id)
    room = next((r for r in plan.get("rooms", []) if r.get("id") == room_id), None)
    if room is None:
        raise HTTPException(status_code=404, detail=f"room {room_id} not found")
    if patch.name is not None:
        room["name"] = patch.name.strip()[:80]
    if patch.type is not None:
        room["type"] = normalise_type(patch.type, room.get("name"))
    report = _revalidate(plan)
    return {"plan": plan, "validation": report}


@app.post("/api/plans/{plan_id}/openings")
def add_opening(plan_id: str, body: OpeningCreate):
    plan = _get_plan(plan_id)
    wall = next((w for w in plan.get("walls", []) if w.get("id") == body.wall), None)
    if wall is None:
        raise HTTPException(status_code=404, detail=f"wall {body.wall} not found")
    scale = scale_of(plan)
    length_units = wall_length(plan, wall) / scale
    width_m = body.width if body.width is not None else (0.9 if body.kind == "door" else 1.2)
    width = min(max(width_m / scale, 0.4 / scale), max(length_units * 0.8, 0.5 / scale))
    if body.offset is None:
        offset = (length_units - width) / 2
    else:
        offset = body.offset / scale
    offset = min(max(offset, 0.02 / scale), max(0.02 / scale, length_units - width - 0.02 / scale))
    opening = {
        "id": max([o.get("id", -1) for o in plan.get("openings", [])] + [-1]) + 1,
        "kind": body.kind,
        "wall": wall["id"],
        "offset": round(offset, 4),
        "width": round(width, 4),
        "sill": 0.0 if body.kind == "door" else (body.sill if body.sill is not None else 0.9),
        "height": body.height if body.height is not None else (2.05 if body.kind == "door" else 1.2),
    }
    plan.setdefault("openings", []).append(opening)
    report = _revalidate(plan)
    return {"plan": plan, "validation": report, "opening": opening}


@app.patch("/api/plans/{plan_id}/openings/{opening_id}")
def patch_opening(plan_id: str, opening_id: int, patch: OpeningPatch):
    plan = _get_plan(plan_id)
    opening = next((o for o in plan.get("openings", []) if o.get("id") == opening_id), None)
    if opening is None:
        raise HTTPException(status_code=404, detail=f"opening {opening_id} not found")
    scale = scale_of(plan)
    if patch.kind is not None:
        opening["kind"] = patch.kind
        if patch.kind == "door":
            opening["sill"] = 0.0
        elif float(opening.get("sill") or 0) < 0.2:
            opening["sill"] = 0.9
    if patch.wall is not None:
        if not any(w.get("id") == patch.wall for w in plan.get("walls", [])):
            raise HTTPException(status_code=404, detail=f"wall {patch.wall} not found")
        opening["wall"] = patch.wall
    if patch.offset is not None:
        opening["offset"] = round(patch.offset / scale, 4)
    if patch.width is not None:
        opening["width"] = round(max(patch.width, 0.3) / scale, 4)
    if patch.sill is not None:
        opening["sill"] = max(0.0, patch.sill)
    if patch.height is not None:
        opening["height"] = max(0.4, patch.height)
    report = _revalidate(plan)
    return {"plan": plan, "validation": report, "opening": opening}


@app.delete("/api/plans/{plan_id}/openings/{opening_id}")
def delete_opening(plan_id: str, opening_id: int):
    plan = _get_plan(plan_id)
    before = len(plan.get("openings", []))
    plan["openings"] = [o for o in plan.get("openings", []) if o.get("id") != opening_id]
    if len(plan["openings"]) == before:
        raise HTTPException(status_code=404, detail=f"opening {opening_id} not found")
    report = _revalidate(plan)
    return {"plan": plan, "validation": report}


# ---------------------------------------------------------------------------
# F3
# ---------------------------------------------------------------------------


@app.post("/api/plans/{plan_id}/validate")
def validate_plan(plan_id: str, body: ValidateRequest | None = None):
    plan = _get_plan(plan_id)
    repair = bool(body.repair) if body else False
    report = _revalidate(plan, repair=repair)
    return {"plan": plan, "validation": report}


# ---------------------------------------------------------------------------
# F5
# ---------------------------------------------------------------------------


@app.get("/api/plans/{plan_id}/scene.glb")
def scene_glb(plan_id: str):
    plan = _get_plan(plan_id)
    try:
        data = build_glb(plan)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not build the 3D scene: {exc}") from exc
    return Response(
        content=data,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'inline; filename="{plan_id}.glb"', "Cache-Control": "no-store"},
    )


@app.get("/api/plans/{plan_id}/export.json")
def export_json(plan_id: str):
    plan = _get_plan(plan_id)
    return JSONResponse(plan, headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'})


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

if FRONTEND.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND)), name="frontend")


@app.get("/")
def index():
    target = FRONTEND / "app.html"
    if not target.exists():
        return {"service": "Plan2Walk", "docs": "/docs"}
    return FileResponse(target)
