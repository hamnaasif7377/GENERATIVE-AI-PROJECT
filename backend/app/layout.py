"""Shared layout helpers for Plan2Walk.

A layout is a plain JSON-serialisable dict in the same shape as the converted
CubiCasa5K plans, so the existing deterministic 3D builder can consume it:

    plan_id, units, grid, plan_width_m, wall_height,
    vertices: [[x, y], ...],
    walls:    [{id, a, b, cls, thickness}],
    rooms:    [{id, type, name, polygon: [[x, y], ...]}],
    openings: [{id, kind, wall, offset, width, sill, height}]

Generated plans are stored in metres (units == "m", grid == 1, plan_width_m == 1).
Converted plans are stored in plan units and are converted with
``scale_of(plan)`` (metres per plan unit).
"""

from __future__ import annotations

import math
import re
from typing import Iterable

ROOM_TYPES = (
    "living_room",
    "kitchen",
    "bedroom",
    "bathroom",
    "hall",
    "other",
)

ROOM_LABELS = {
    "living_room": "Living room",
    "kitchen": "Kitchen",
    "bedroom": "Bedroom",
    "bathroom": "Bathroom",
    "hall": "Hall",
    "other": "Room",
}

# Fallback relative areas when the planner does not provide a weight.
TYPE_WEIGHT = {
    "living_room": 3.2,
    "kitchen": 2.0,
    "bedroom": 2.4,
    "bathroom": 1.1,
    "hall": 1.2,
    "other": 1.5,
}

TYPE_ALIASES = {
    "living": "living_room",
    "lounge": "living_room",
    "sitting": "living_room",
    "dining": "living_room",
    "kitchen": "kitchen",
    "bed": "bedroom",
    "bedroom": "bedroom",
    "master": "bedroom",
    "bath": "bathroom",
    "bathroom": "bathroom",
    "wc": "bathroom",
    "toilet": "bathroom",
    "hall": "hall",
    "hallway": "hall",
    "corridor": "hall",
    "entry": "hall",
    "lobby": "hall",
    "garage": "other",
    "store": "other",
    "storage": "other",
    "balcony": "other",
    "terrace": "other",
    "office": "other",
    "study": "other",
    "utility": "other",
    "laundry": "other",
}


def scale_of(plan: dict) -> float:
    """Metres per plan unit."""
    grid = float(plan.get("grid") or 1000.0)
    if plan.get("units") == "m":
        return 1.0
    width = float(plan.get("plan_width_m") or 15.0)
    return width / grid


def normalise_type(value: str | None, name: str | None = None) -> str:
    """Pick a room type, trusting strong words in the room name first.

    The name is usually more reliable than the model's ``type`` field (e.g. a
    room called "Master Bathroom" must not become a bedroom just because the
    model wrote "master").
    """
    name_text = (name or "").lower()
    for key in (
        "bath",
        "wc",
        "toilet",
        "shower",
        "kitchen",
        "bedroom",
        "bed",
        "living",
        "lounge",
        "sitting",
        "dining",
        "hall",
        "corridor",
        "entry",
        "lobby",
        "office",
        "study",
        "garage",
        "store",
        "storage",
        "balcony",
        "terrace",
        "utility",
        "laundry",
    ):
        if key in name_text:
            return TYPE_ALIASES[key]
    text = (value or "").lower()
    if text in ROOM_TYPES:
        return text
    for key, room_type in TYPE_ALIASES.items():
        if key in text:
            return room_type
    return "other"


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", (text or "plan").lower()).strip("_")
    return value[:48] or "plan"


def polygon_area(polygon: Iterable[Iterable[float]]) -> float:
    points = list(polygon)
    if len(points) < 3:
        return 0.0
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0


def polygon_centroid(polygon: Iterable[Iterable[float]]) -> tuple[float, float]:
    points = list(polygon)
    if not points:
        return 0.0, 0.0
    area = 0.0
    cx = 0.0
    cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < 1e-9:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    area *= 0.5
    return cx / (6 * area), cy / (6 * area)


def wall_points(plan: dict, wall: dict) -> tuple[tuple[float, float], tuple[float, float]]:
    a = plan["vertices"][wall["a"]]
    b = plan["vertices"][wall["b"]]
    return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))


def wall_length(plan: dict, wall: dict, scale: float | None = None) -> float:
    (ax, ay), (bx, by) = wall_points(plan, wall)
    return math.hypot(bx - ax, by - ay) * (scale_of(plan) if scale is None else scale)


def point_on_wall(plan: dict, wall: dict, offset_m: float) -> tuple[float, float]:
    """Point ``offset_m`` metres along a wall, in plan units."""
    (ax, ay), (bx, by) = wall_points(plan, wall)
    length = math.hypot(bx - ax, by - ay)
    if length < 1e-9:
        return ax, ay
    t = offset_m / (length * scale_of(plan))
    t = min(max(t, 0.0), 1.0)
    return ax + (bx - ax) * t, ay + (by - ay) * t


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def room_at(plan: dict, x: float, y: float) -> dict | None:
    for room in plan.get("rooms", []):
        if point_in_polygon(x, y, room.get("polygon", [])):
            return room
    return None


def room_area_m2(plan: dict, room: dict) -> float:
    scale = scale_of(plan)
    return polygon_area(room.get("polygon", [])) * scale * scale


def room_label(room: dict) -> str:
    return room.get("name") or ROOM_LABELS.get(room.get("type", "other"), "Room")


def plan_metrics(plan: dict) -> dict:
    scale = scale_of(plan)
    areas = [room_area_m2(plan, r) for r in plan.get("rooms", [])]
    doors = [o for o in plan.get("openings", []) if o.get("kind") == "door"]
    windows = [o for o in plan.get("openings", []) if o.get("kind") == "window"]
    return {
        "rooms": len(plan.get("rooms", [])),
        "walls": len(plan.get("walls", [])),
        "openings": len(plan.get("openings", [])),
        "doors": len(doors),
        "windows": len(windows),
        "area_m2": round(sum(areas), 1),
        "min_room_m2": round(min(areas), 1) if areas else 0.0,
        "wall_height_m": plan.get("wall_height", 2.7),
        "scale_m_per_unit": scale,
    }


def new_plan_id(title: str) -> str:
    import secrets

    return f"{slug(title)}-{secrets.token_hex(3)}"
