"""Deterministic room packing and wall-graph construction.

The language model only produces a *room program* (names, types, relative sizes,
zones).  This module turns that program into a rectilinear, gap-free plan and a
wall graph with door/window openings.  Geometry is therefore always valid even
when the model's numbers are rough.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .layout import (
    TYPE_WEIGHT,
    normalise_type,
    polygon_area,
    scale_of,
)

QUANT = 0.05  # metres


# ---------------------------------------------------------------------------
# Squarified treemap (Bruls, Huizing & van Wijk) adapted to metres.
# ---------------------------------------------------------------------------


def _layout_row(sizes, x, y, dx, dy):
    covered = sum(sizes)
    width = covered / dy if dy else 0.0
    rects = []
    for size in sizes:
        height = size / width if width else 0.0
        rects.append({"x": x, "y": y, "w": width, "h": height})
        y += height
    return rects


def _layout_col(sizes, x, y, dx, dy):
    covered = sum(sizes)
    height = covered / dx if dx else 0.0
    rects = []
    for size in sizes:
        width = size / height if height else 0.0
        rects.append({"x": x, "y": y, "w": width, "h": height})
        x += width
    return rects


def _layout(sizes, x, y, dx, dy):
    return _layout_row(sizes, x, y, dx, dy) if dx >= dy else _layout_col(sizes, x, y, dx, dy)


def _leftover(sizes, x, y, dx, dy):
    if dx >= dy:
        covered = sum(sizes)
        width = covered / dy if dy else 0.0
        return x + width, y, dx - width, dy
    covered = sum(sizes)
    height = covered / dx if dx else 0.0
    return x, y + height, dx, dy - height


def _worst_ratio(sizes, x, y, dx, dy):
    ratios = []
    for rect in _layout(sizes, x, y, dx, dy):
        if rect["w"] <= 1e-9 or rect["h"] <= 1e-9:
            return float("inf")
        ratios.append(max(rect["w"] / rect["h"], rect["h"] / rect["w"]))
    return max(ratios) if ratios else float("inf")


def squarify(sizes, x, y, dx, dy):
    """Tile (x, y, dx, dy) with rectangles whose areas follow ``sizes``."""
    sizes = [max(float(s), 1e-6) for s in sizes]
    if not sizes:
        return []
    total = sum(sizes)
    area = dx * dy
    sizes = [s * area / total for s in sizes]
    if len(sizes) == 1:
        return [{"x": x, "y": y, "w": dx, "h": dy}]

    i = 1
    while i < len(sizes) and _worst_ratio(sizes[:i], x, y, dx, dy) >= _worst_ratio(
        sizes[: i + 1], x, y, dx, dy
    ):
        i += 1
    current = sizes[:i]
    remaining = sizes[i:]
    return _layout(current, x, y, dx, dy) + squarify(
        remaining, *_leftover(current, x, y, dx, dy)
    )


# ---------------------------------------------------------------------------
# Program normalisation
# ---------------------------------------------------------------------------

BAND_RANK = {"back": 0, "rear": 0, "middle": 1, "center": 1, "centre": 1, "left": 1, "right": 1, "front": 2}


def default_windows(room_type: str) -> int:
    return {"living_room": 2, "bedroom": 1, "kitchen": 1, "bathroom": 1, "hall": 0}.get(room_type, 0)


def _as_float(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalise_program(program: dict, prompt: str = "", seed: int = 0) -> dict:
    program = dict(program or {})
    plot = dict(program.get("plot") or {})
    width = _as_float(plot.get("width_m") or plot.get("width"), 12.0)
    depth = _as_float(plot.get("depth_m") or plot.get("depth"), 10.0)
    width = min(max(width, 6.0), 30.0)
    depth = min(max(depth, 6.0), 30.0)

    raw_rooms = program.get("rooms") or []
    rooms = []
    for i, raw in enumerate(raw_rooms):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("label") or f"Room {i + 1}").strip()
        room_type = normalise_type(raw.get("type"), name)
        weight = _as_float(raw.get("weight") or raw.get("area_m2") or raw.get("area"), TYPE_WEIGHT[room_type])
        weight = min(max(weight, 0.6), 8.0)
        windows = raw.get("windows")
        windows = default_windows(room_type) if windows is None else int(_as_float(windows, 0))
        windows = min(max(windows, 0), 4)
        zone = str(raw.get("zone") or "").lower().strip()
        rooms.append(
            {
                "name": name,
                "type": room_type,
                "weight": weight,
                "zone": zone,
                "windows": windows,
                "doors": int(_as_float(raw.get("doors"), 1)),
            }
        )
    if not rooms:
        rooms = [
            {"name": "Living room", "type": "living_room", "weight": 3.2, "zone": "front", "windows": 2, "doors": 1},
            {"name": "Kitchen", "type": "kitchen", "weight": 2.0, "zone": "front", "windows": 1, "doors": 1},
            {"name": "Bedroom", "type": "bedroom", "weight": 2.4, "zone": "back", "windows": 1, "doors": 1},
            {"name": "Bathroom", "type": "bathroom", "weight": 1.1, "zone": "middle", "windows": 1, "doors": 1},
            {"name": "Hall", "type": "hall", "weight": 1.2, "zone": "middle", "windows": 0, "doors": 2},
        ]
    rooms = rooms[:16]

    # Guarantee enough floor area for the requested rooms (>= 8.5 m² each).
    need = len(rooms) * 8.5
    if width * depth < need:
        factor = math.sqrt(need / (width * depth))
        width = min(width * factor, 30.0)
        depth = min(depth * factor, 30.0)

    entrance = str(program.get("entrance") or "").strip()
    if not entrance:
        for room in rooms:
            if room["type"] == "hall":
                entrance = room["name"]
                break
        else:
            entrance = rooms[0]["name"]

    title = str(program.get("title") or "Generated home").strip() or "Generated home"
    return {
        "title": title,
        "summary": str(program.get("summary") or "").strip(),
        "plot": {"width_m": round(width, 2), "depth_m": round(depth, 2)},
        "rooms": rooms,
        "entrance": entrance,
        "notes": str(program.get("notes") or "").strip(),
        "variant": int(seed),
    }


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------


def _quant(value: float) -> float:
    return round(value / QUANT) * QUANT


def pack_rooms(program: dict, seed: int = 0) -> list[dict]:
    plot = program["plot"]
    width = _quant(float(plot["width_m"]))
    depth = _quant(float(plot["depth_m"]))
    rooms = program["rooms"]

    order = sorted(
        range(len(rooms)),
        key=lambda i: (BAND_RANK.get(rooms[i].get("zone", ""), 1), -rooms[i]["weight"], i),
    )
    if seed:
        # Deterministic variation for "another option": rotate the order inside
        # each band without changing the room program.
        bands = defaultdict(list)
        for idx in order:
            bands[BAND_RANK.get(rooms[idx].get("zone", ""), 1)].append(idx)
        order = []
        for band in sorted(bands):
            items = bands[band]
            shift = seed % len(items) if items else 0
            order.extend(items[shift:] + items[:shift])

    sizes = [rooms[i]["weight"] for i in order]
    rects = squarify(sizes, 0.0, 0.0, width, depth)

    packed: list[dict | None] = [None] * len(rooms)
    for idx, rect in zip(order, rects):
        x0 = _quant(rect["x"])
        y0 = _quant(rect["y"])
        x1 = _quant(rect["x"] + rect["w"])
        y1 = _quant(rect["y"] + rect["h"])
        x0 = min(max(x0, 0.0), width)
        y0 = min(max(y0, 0.0), depth)
        x1 = min(max(x1, x0 + QUANT), width)
        y1 = min(max(y1, y0 + QUANT), depth)
        packed[idx] = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
    return [r for r in packed if r is not None]


# ---------------------------------------------------------------------------
# Wall graph
# ---------------------------------------------------------------------------


def _room_at(rects: list[dict], x: float, y: float, eps: float = 0.005) -> int | None:
    for i, r in enumerate(rects):
        if r["x"] - eps <= x <= r["x"] + r["w"] + eps and r["y"] - eps <= y <= r["y"] + r["h"] + eps:
            return i
    return None


def _merge(segments: list[list], axis: int) -> list[list]:
    """Merge contiguous segments that separate the same pair of rooms."""
    segments.sort(key=lambda s: (s[0], s[1]))
    merged: list[list] = []
    for seg in segments:
        if merged:
            last = merged[-1]
            if (
                abs(last[0] - seg[0]) < 1e-6
                and abs(last[2] - seg[1]) < 1e-6
                and last[3] == seg[3]
                and last[4] == seg[4]
            ):
                last[2] = seg[2]
                continue
        merged.append(list(seg))
    return merged


def build_walls(rects: list[dict], width: float, depth: float) -> list[dict]:
    xs = sorted({0.0, width} | {r["x"] for r in rects} | {r["x"] + r["w"] for r in rects})
    ys = sorted({0.0, depth} | {r["y"] for r in rects} | {r["y"] + r["h"] for r in rects})
    eps = 0.02

    vertical: list[list] = []
    for x in xs:
        for y0, y1 in zip(ys, ys[1:]):
            if y1 - y0 < 1e-6:
                continue
            mid = (y0 + y1) / 2
            left = _room_at(rects, x - eps, mid)
            right = _room_at(rects, x + eps, mid)
            if left != right:
                vertical.append([x, y0, y1, left, right])
    vertical = _merge(vertical, axis=0)

    horizontal: list[list] = []
    for y in ys:
        for x0, x1 in zip(xs, xs[1:]):
            if x1 - x0 < 1e-6:
                continue
            mid = (x0 + x1) / 2
            top = _room_at(rects, mid, y - eps)
            bottom = _room_at(rects, mid, y + eps)
            if top != bottom:
                horizontal.append([y, x0, x1, top, bottom])
    horizontal = _merge(horizontal, axis=1)

    vertices: list[list[float]] = []
    index: dict[tuple[float, float], int] = {}

    def vertex(x: float, y: float) -> int:
        key = (round(x, 3), round(y, 3))
        if key not in index:
            index[key] = len(vertices)
            vertices.append([round(x, 3), round(y, 3)])
        return index[key]

    walls: list[dict] = []
    for x, y0, y1, left, right in vertical:
        walls.append(
            {
                "id": len(walls),
                "a": vertex(x, y0),
                "b": vertex(x, y1),
                "cls": "exterior" if left is None or right is None else "interior",
                "thickness": 0.20 if left is None or right is None else 0.10,
                "adjacent_rooms": [left, right],
            }
        )
    for y, x0, x1, top, bottom in horizontal:
        walls.append(
            {
                "id": len(walls),
                "a": vertex(x0, y),
                "b": vertex(x1, y),
                "cls": "exterior" if top is None or bottom is None else "interior",
                "thickness": 0.20 if top is None or bottom is None else 0.10,
                "adjacent_rooms": [top, bottom],
            }
        )
    return walls, vertices


# ---------------------------------------------------------------------------
# Openings
# ---------------------------------------------------------------------------


def _wall_length(vertices: list[list[float]], wall: dict) -> float:
    ax, ay = vertices[wall["a"]]
    bx, by = vertices[wall["b"]]
    return math.hypot(bx - ax, by - ay)


def _free_slot(length: float, width: float, preferred: float, used: list[tuple[float, float]]) -> float | None:
    if width > length - 0.1:
        width = max(0.4, length - 0.1)
    low = 0.05
    high = max(low, length - width - 0.05)
    preferred = min(max(preferred - width / 2, low), high)

    def is_free(start: float) -> bool:
        end = start + width
        return all(end <= u0 - 0.06 or start >= u1 + 0.06 for u0, u1 in used)

    if is_free(preferred):
        return preferred
    steps = max(1, int((high - low) / 0.05))
    for i in range(steps + 1):
        for start in (preferred + i * 0.05, preferred - i * 0.05):
            if low <= start <= high and is_free(start):
                return start
    return None


def place_openings(
    plan: dict,
    program: dict,
    walls: list[dict],
    vertices: list[list[float]],
) -> list[dict]:
    rooms = plan["rooms"]
    by_id = {w["id"]: w for w in walls}
    room_walls: dict[int, list[int]] = defaultdict(list)
    for wall in walls:
        left, right = wall.get("adjacent_rooms") or [None, None]
        if left is not None:
            room_walls[left].append(wall["id"])
        if right is not None:
            room_walls[right].append(wall["id"])

    used: dict[int, list[tuple[float, float]]] = defaultdict(list)
    openings: list[dict] = []

    def add(wall_id: int, kind: str, width: float, preferred: float, sill: float, height: float) -> bool:
        wall = by_id[wall_id]
        length = _wall_length(vertices, wall)
        start = _free_slot(length, width, preferred, used[wall_id])
        if start is None:
            return False
        used[wall_id].append((start, start + width))
        openings.append(
            {
                "id": len(openings),
                "kind": kind,
                "wall": wall_id,
                "offset": round(start, 2),
                "width": round(min(width, length - start - 0.05), 2),
                "sill": sill,
                "height": height,
            }
        )
        return True

    # --- entrance: a door on an exterior wall of the entrance room ----------
    entrance_name = str(program.get("entrance") or "").lower()
    entrance = 0
    for i, room in enumerate(rooms):
        if entrance_name and entrance_name in f"{room.get('name','')} {room.get('type','')}".lower():
            entrance = i
            break
    else:
        for i, room in enumerate(rooms):
            if room.get("type") == "hall":
                entrance = i
                break

    exterior = [
        wid
        for wid in room_walls[entrance]
        if by_id[wid]["cls"] == "exterior"
    ]
    if exterior:
        wid = max(exterior, key=lambda w: _wall_length(vertices, by_id[w]))
        add(wid, "door", 0.95, _wall_length(vertices, by_id[wid]) / 2, 0.0, 2.05)

    # --- doors: spanning tree over the room-adjacency graph -----------------
    visited = {entrance}
    while len(visited) < len(rooms):
        progress = False
        for room in range(len(rooms)):
            if room in visited:
                continue
            candidates = []
            for wid in room_walls[room]:
                wall = by_id[wid]
                left, right = wall.get("adjacent_rooms") or [None, None]
                other = right if left == room else left
                if wall["cls"] == "interior" and other in visited:
                    candidates.append((wid, other))
            if candidates:
                wid, _ = max(candidates, key=lambda c: _wall_length(vertices, by_id[c[0]]))
                length = _wall_length(vertices, by_id[wid])
                add(wid, "door", 0.85, length / 2, 0.0, 2.05)
                visited.add(room)
                progress = True
        if not progress:
            break

    # --- windows on exterior walls -----------------------------------------
    for room_id, room in enumerate(rooms):
        wanted = int((program["rooms"][room_id].get("windows") if room_id < len(program["rooms"]) else 0) or 0)
        if wanted <= 0:
            continue
        walls_out = [
            wid for wid in room_walls[room_id] if by_id[wid]["cls"] == "exterior"
        ]
        walls_out.sort(key=lambda w: _wall_length(vertices, by_id[w]), reverse=True)
        if not walls_out:
            continue
        placed = 0
        for wid in walls_out:
            length = _wall_length(vertices, by_id[wid])
            width = min(1.4, max(0.6, length * 0.55))
            if placed >= wanted:
                break
            slots = 1 if length < 2.4 else 2
            for k in range(slots):
                if placed >= wanted:
                    break
                preferred = length * (k + 1) / (slots + 1)
                if add(wid, "window", width, preferred, 0.9, 1.2):
                    placed += 1
    return openings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def program_to_layout(program: dict, plan_id: str, seed: int = 0) -> dict:
    program = normalise_program(program, seed=seed)
    rects = pack_rooms(program, seed=seed)
    width = _quant(float(program["plot"]["width_m"]))
    depth = _quant(float(program["plot"]["depth_m"]))
    walls, vertices = build_walls(rects, width, depth)

    rooms = []
    for i, (room, rect) in enumerate(zip(program["rooms"], rects)):
        polygon = [
            [round(rect["x"], 3), round(rect["y"], 3)],
            [round(rect["x"] + rect["w"], 3), round(rect["y"], 3)],
            [round(rect["x"] + rect["w"], 3), round(rect["y"] + rect["h"], 3)],
            [round(rect["x"], 3), round(rect["y"] + rect["h"], 3)],
        ]
        rooms.append(
            {
                "id": i,
                "type": room["type"],
                "name": room["name"],
                "source_name": room["name"],
                "windows": room.get("windows", 0),
                "doors": room.get("doors", 1),
                "polygon": polygon,
                "area_m2": round(polygon_area(polygon), 2),
            }
        )

    plan = {
        "plan_id": plan_id,
        "title": program["title"],
        "units": "m",
        "grid": 1.0,
        "plan_width_m": 1.0,
        "wall_height": 2.7,
        "plot": program["plot"],
        "vertices": vertices,
        "walls": walls,
        "rooms": rooms,
        "openings": [],
        "program": program,
        "source": "generated",
    }
    plan["openings"] = place_openings(plan, program, walls, vertices)
    return plan
