"""F3: layout validation and small automatic repairs.

Checks the rules from the proposal: closed rooms, shared walls, no overlaps,
openings on walls, every room reachable.  Problems that can be fixed safely are
repaired (clamped openings, added doors); the rest are reported.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque

from shapely.geometry import Polygon

from .layout import plan_metrics, room_at, room_label, scale_of, wall_points

MIN_ROOM_M2 = 1.5
OVERLAP_TOL_M2 = 0.15
DOOR_MIN_M = 0.55
DOOR_MAX_M = 2.4
WINDOW_MIN_M = 0.4


def _issue(code: str, message: str, entity=None, severity: str = "error") -> dict:
    return {"code": code, "message": message, "entity": entity, "severity": severity}


def _polygon(points, scale: float) -> Polygon | None:
    if not points or len(points) < 3:
        return None
    poly = Polygon([(x * scale, y * scale) for x, y in points])
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if not poly.is_empty else None


def wall_adjacent_rooms(plan: dict, wall: dict) -> tuple[int | None, int | None]:
    """Rooms on either side of a wall, using metadata or geometry."""
    pair = wall.get("adjacent_rooms")
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        return pair[0], pair[1]
    scale = scale_of(plan)
    (ax, ay), (bx, by) = wall_points(plan, wall)
    length = math.hypot(bx - ax, by - ay)
    if length < 1e-9:
        return None, None
    mx, my = (ax + bx) / 2, (ay + by) / 2
    nx, ny = -(by - ay) / length, (bx - ax) / length
    probe = 0.35 / scale
    rooms = plan.get("rooms", [])
    left = room_at(plan, mx + nx * probe, my + ny * probe)
    right = room_at(plan, mx - nx * probe, my - ny * probe)
    left_id = left.get("id") if left else None
    right_id = right.get("id") if right else None
    return left_id, right_id


def _entrance_room(plan: dict) -> int:
    rooms = plan.get("rooms", [])
    if not rooms:
        return 0
    program = plan.get("program") or {}
    wanted = str(program.get("entrance") or "").lower()
    for room in rooms:
        if wanted and wanted in f"{room.get('name','')} {room.get('type','')}".lower():
            return room.get("id", 0)
    for room in rooms:
        if room.get("type") == "hall":
            return room.get("id", 0)
    return rooms[0].get("id", 0)


def _door_edges(plan: dict) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = defaultdict(set)
    walls = {w["id"]: w for w in plan.get("walls", [])}
    for opening in plan.get("openings", []):
        if opening.get("kind") != "door":
            continue
        wall = walls.get(opening.get("wall"))
        if not wall:
            continue
        left, right = wall_adjacent_rooms(plan, wall)
        if left is not None and right is not None and left != right:
            graph[left].add(right)
            graph[right].add(left)
    return graph


def _reachable(plan: dict) -> set[int]:
    graph = _door_edges(plan)
    start = _entrance_room(plan)
    seen = {start}
    queue = deque([start])
    while queue:
        room = queue.popleft()
        for other in graph.get(room, ()):
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return seen


def validate(plan: dict, repair: bool = False) -> dict:
    repairs: list[dict] = []
    if repair:
        _repair_openings(plan, repairs)
        _repair_access(plan, repairs)

    errors: list[dict] = []
    warnings: list[dict] = []
    scale = scale_of(plan)
    wall_height = float(plan.get("wall_height") or 2.7)
    vertices = plan.get("vertices") or []
    walls = plan.get("walls") or []
    rooms = plan.get("rooms") or []
    openings = plan.get("openings") or []

    # --- structural --------------------------------------------------------
    if not rooms:
        errors.append(_issue("no_rooms", "The layout has no rooms."))
    if not walls:
        errors.append(_issue("no_walls", "The layout has no walls."))

    room_ids = [r.get("id") for r in rooms]
    if len(set(room_ids)) != len(room_ids):
        errors.append(_issue("duplicate_room_ids", "Room ids are not unique."))
    wall_ids = [w.get("id") for w in walls]
    if len(set(wall_ids)) != len(wall_ids):
        errors.append(_issue("duplicate_wall_ids", "Wall ids are not unique."))
    opening_ids = [o.get("id") for o in openings]
    if len(set(opening_ids)) != len(opening_ids):
        errors.append(_issue("duplicate_opening_ids", "Opening ids are not unique."))

    # --- walls -------------------------------------------------------------
    wall_lengths: dict[int, float] = {}
    for wall in walls:
        a, b = wall.get("a"), wall.get("b")
        if not isinstance(a, int) or not isinstance(b, int) or a >= len(vertices) or b >= len(vertices) or a < 0 or b < 0:
            errors.append(_issue("bad_wall_vertices", f"Wall {wall.get('id')} references a missing vertex.", wall.get("id")))
            continue
        (ax, ay), (bx, by) = wall_points(plan, wall)
        length_m = math.hypot(bx - ax, by - ay) * scale
        wall_lengths[wall["id"]] = length_m
        if length_m < 0.08:
            errors.append(_issue("degenerate_wall", f"Wall {wall.get('id')} is shorter than 8 cm.", wall.get("id")))

    # --- rooms -------------------------------------------------------------
    polys: dict[int, Polygon] = {}
    for room in rooms:
        poly = _polygon(room.get("polygon") or [], scale)
        if poly is None:
            errors.append(_issue("bad_room_polygon", f"Room {room.get('id')} has no valid polygon.", room.get("id")))
            continue
        polys[room.get("id")] = poly
        if poly.area < MIN_ROOM_M2:
            errors.append(
                _issue(
                    "room_too_small",
                    f"{room_label(room)} is {poly.area:.1f} m² (minimum {MIN_ROOM_M2} m²).",
                    room.get("id"),
                )
            )
        if not (room.get("name") or "").strip():
            warnings.append(_issue("missing_room_name", f"Room {room.get('id')} has no name.", room.get("id"), "warning"))

    ids = list(polys)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            overlap = polys[a].intersection(polys[b]).area
            if overlap > OVERLAP_TOL_M2:
                errors.append(
                    _issue(
                        "room_overlap",
                        f"Rooms {a} and {b} overlap by {overlap:.2f} m².",
                        [a, b],
                    )
                )

    # --- openings ----------------------------------------------------------
    walls_by_id = {w["id"]: w for w in walls}
    per_wall: dict[int, list[tuple[float, float, int]]] = defaultdict(list)
    for opening in openings:
        oid = opening.get("id")
        wall = walls_by_id.get(opening.get("wall"))
        if wall is None:
            errors.append(_issue("opening_without_wall", f"Opening {oid} is on a missing wall.", oid))
            continue
        length = wall_lengths.get(wall["id"], 0.0)
        width = float(opening.get("width") or 0.0) * scale
        offset = float(opening.get("offset") or 0.0) * scale
        kind = opening.get("kind")
        sill = float(opening.get("sill") or 0.0)
        height = float(opening.get("height") or 0.0)

        if width <= 0:
            errors.append(_issue("opening_zero_width", f"Opening {oid} has zero width.", oid))
        if kind == "door" and not (DOOR_MIN_M <= width <= DOOR_MAX_M):
            errors.append(_issue("door_width", f"Door {oid} is {width:.2f} m wide.", oid))
        if kind == "window" and width < WINDOW_MIN_M:
            errors.append(_issue("window_width", f"Window {oid} is {width:.2f} m wide.", oid))
        if offset < -0.01 or offset + width > length + 0.01:
            errors.append(
                _issue(
                    "opening_outside_wall",
                    f"Opening {oid} spans {offset:.2f}–{offset + width:.2f} m on a {length:.2f} m wall.",
                    oid,
                )
            )
        if kind == "door" and sill > 0.05:
            errors.append(_issue("door_sill", f"Door {oid} has a {sill:.2f} m sill.", oid))
        if kind == "window" and sill < 0.2:
            warnings.append(_issue("window_sill", f"Window {oid} starts at {sill:.2f} m.", oid, "warning"))
        if height > wall_height + 0.01:
            errors.append(_issue("opening_too_tall", f"Opening {oid} is taller than the wall.", oid))
        per_wall[wall["id"]].append((offset, offset + width, oid))

    for wall_id, spans in per_wall.items():
        spans.sort()
        for (a0, a1, aid), (b0, b1, bid) in zip(spans, spans[1:]):
            if b0 < a1 - 0.02:
                errors.append(
                    _issue(
                        "opening_overlap",
                        f"Openings {aid} and {bid} overlap on wall {wall_id}.",
                        [aid, bid],
                    )
                )

    # --- access ------------------------------------------------------------
    if rooms:
        seen = _reachable(plan)
        for room in rooms:
            if room.get("id") not in seen:
                errors.append(
                    _issue(
                        "room_unreachable",
                        f"{room_label(room)} cannot be reached through doors.",
                        room.get("id"),
                    )
                )

    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "repairs": repairs,
        "metrics": plan_metrics(plan),
    }
    return report


# ---------------------------------------------------------------------------
# Repairs
# ---------------------------------------------------------------------------


def _repair_openings(plan: dict, repairs: list[dict]) -> None:
    scale = scale_of(plan)
    wall_height = float(plan.get("wall_height") or 2.7)
    walls = {w["id"]: w for w in plan.get("walls", [])}
    vertices = plan.get("vertices") or []
    lengths = {}
    for wid, wall in walls.items():
        (ax, ay), (bx, by) = wall_points(plan, wall)
        lengths[wid] = math.hypot(bx - ax, by - ay) * scale

    used: dict[int, list[tuple[float, float]]] = defaultdict(list)
    kept = []
    for opening in plan.get("openings", []):
        wid = opening.get("wall")
        if wid not in walls:
            repairs.append({"code": "drop_opening", "message": f"Dropped opening {opening.get('id')} on a missing wall."})
            continue
        length = lengths[wid]
        width = float(opening.get("width") or 0.0) * scale
        offset = float(opening.get("offset") or 0.0) * scale
        if width <= 0.05:
            repairs.append({"code": "drop_opening", "message": f"Dropped zero-width opening {opening.get('id')}."})
            continue
        width = min(width, max(0.4, length - 0.1))
        offset = min(max(offset, 0.02), max(0.02, length - width - 0.02))
        if opening.get("kind") == "door":
            opening["sill"] = 0.0
            width = min(max(width, DOOR_MIN_M), min(DOOR_MAX_M, length - 0.1))
        if float(opening.get("height") or 0) > wall_height:
            opening["height"] = round(wall_height - 0.05, 2)
        opening["width"] = round(width / scale, 3)
        opening["offset"] = round(offset / scale, 3)
        if any(offset < u1 - 0.02 and offset + width > u0 + 0.02 for u0, u1 in used[wid]):
            repairs.append({"code": "drop_opening", "message": f"Dropped overlapping opening {opening.get('id')}."})
            continue
        used[wid].append((offset, offset + width))
        kept.append(opening)
    plan["openings"] = kept


def _repair_access(plan: dict, repairs: list[dict]) -> None:
    rooms = plan.get("rooms", [])
    if len(rooms) < 2:
        return
    walls = plan.get("walls", [])
    vertices = plan.get("vertices") or []
    scale = scale_of(plan)
    start = _entrance_room(plan)

    for _ in range(len(rooms) + 1):
        seen = _reachable(plan)
        missing = [r for r in rooms if r.get("id") not in seen]
        if not missing:
            return
        target = missing[0].get("id")
        candidates = []
        for wall in walls:
            left, right = wall_adjacent_rooms(plan, wall)
            if left == target and right in seen:
                candidates.append(wall)
            elif right == target and left in seen:
                candidates.append(wall)
        if not candidates:
            return
        wall = max(
            candidates,
            key=lambda w: math.hypot(
                vertices[w["b"]][0] - vertices[w["a"]][0],
                vertices[w["b"]][1] - vertices[w["a"]][1],
            ),
        )
        (ax, ay), (bx, by) = wall_points(plan, wall)
        length = math.hypot(bx - ax, by - ay)
        width = min(0.9 / scale, length * 0.8)
        opening_id = max([o.get("id", -1) for o in plan.get("openings", [])] + [-1]) + 1
        plan.setdefault("openings", []).append(
            {
                "id": opening_id,
                "kind": "door",
                "wall": wall["id"],
                "offset": round((length - width) / 2, 3),
                "width": round(width, 3),
                "sill": 0.0,
                "height": 2.05,
            }
        )
        repairs.append(
            {
                "code": "add_door",
                "message": f"Added a door on wall {wall['id']} to reach room {target}.",
            }
        )
