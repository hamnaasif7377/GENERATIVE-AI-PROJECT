#!/usr/bin/env python
"""Convert CubiCasa5K plans (model.svg + F1_scaled.png) into the Plan2Walk layout JSON.

Pipeline (per plan):
  1. map room classes to a small set (bedroom, bathroom, kitchen, living_room, hall, other)
  2. read room polygons, grow each by half the median wall thickness so neighbouring
     rooms meet on the wall centreline (CubiCasa room polygons stop at the wall faces)
  3. simplify each room to an orthogonal polygon of <= 8 vertices
  4. snap all coordinates to a shared grid (clusters of nearby x / y values are merged)
  5. build the wall graph from the snapped room edges: shared edges exist once,
     walls are split at every junction, rooms are loops of wall ids
  6. attach each door / window to the nearest wall (wall id, offset, width)

Coordinates in the output are integers on a 0..GRID grid, scaled by the longer image side,
so aspect ratio is kept and no real-world scale is needed.

Usage:
  python scripts/convert_cubicasa.py --root data/raw/cubicasa5k --split test --out data/processed --limit 200
"""
import argparse
import json
import math
import re
import shutil
import statistics
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

GRID = 1000
MAX_VERTS = 8
SKIP_ROOMS = ("outdoor",)
ROOM_KEYWORDS = [
    ("bed", "bedroom"),
    ("bath", "bathroom"),
    ("kitchen", "kitchen"),
    ("living", "living_room"),
    ("dining", "living_room"),
    ("entry", "hall"),
    ("hall", "hall"),
    ("lobby", "hall"),
]


# ----------------------------------------------------------------------------- parsing
def room_type(cls_name):
    s = cls_name.lower()
    for key, val in ROOM_KEYWORDS:
        if key in s:
            return val
    return "other"


def numbers(s):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", s or "")]


def points_of(s):
    n = numbers(s)
    return list(zip(n[0::2], n[1::2]))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def polygon_from_points(s):
    pts = points_of(s)
    if len(pts) < 3:
        return None
    p = Polygon(pts)
    if not p.is_valid:
        p = p.buffer(0)
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    return p if p.geom_type == "Polygon" and p.area > 1 else None


def polygons_in(el):
    """All polygons below (and including) an SVG element, as shapely polygons."""
    out = []
    for e in el.iter():
        if local(e.tag) == "polygon" and e.get("points"):
            p = polygon_from_points(e.get("points"))
            if p is not None:
                out.append(p)
    return out


def wall_polygons(el):
    """Polygons of the wall footprint, skipping Door/Window symbols nested inside it."""
    out = []
    for c in el:
        cls = (c.get("class") or "").split()
        if cls and cls[0] in ("Door", "Window"):
            continue
        if local(c.tag) == "polygon" and c.get("points"):
            p = polygon_from_points(c.get("points"))
            if p is not None:
                out.append(p)
        else:
            out += wall_polygons(c)
    return out


def collect(root):
    items = {"Space": [], "Wall": [], "Door": [], "Window": []}

    def walk(el):
        cls = (el.get("class") or "").split()
        if cls and cls[0] in items:
            items[cls[0]].append(el)
            # keep walking: CubiCasa nests Door/Window groups inside Wall groups
        for c in el:
            walk(c)

    walk(root)
    return items


def wall_thickness(wall_els):
    vals = []
    for el in wall_els:
        for p in wall_polygons(el):
            c = list(p.minimum_rotated_rectangle.exterior.coords)
            vals.append(min(math.dist(c[0], c[1]), math.dist(c[1], c[2])))
    t = statistics.median(vals) if vals else 6.0
    return min(max(t, 2.0), 30.0)


# ------------------------------------------------------------------------ geometry
def orthogonalize(poly, tol):
    """Turn a polygon into an axis-aligned polygon with alternating H/V edges, or None."""
    p = poly.simplify(tol, preserve_topology=True)
    if p.is_empty or p.geom_type != "Polygon":
        return None
    pts = list(p.exterior.coords)[:-1]
    n = len(pts)
    if n < 4:
        return None
    groups = []  # each: [orientation, weighted coord sum, total length]
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        if abs(dx) >= abs(dy):
            o, c = "H", (a[1] + b[1]) / 2
        else:
            o, c = "V", (a[0] + b[0]) / 2
        if groups and groups[-1][0] == o:
            groups[-1][1] += c * length
            groups[-1][2] += length
        else:
            groups.append([o, c * length, length])
    if len(groups) > 1 and groups[0][0] == groups[-1][0]:
        last = groups.pop()
        groups[0][1] += last[1]
        groups[0][2] += last[2]
    if len(groups) < 4 or len(groups) % 2:
        return None
    coords = [(g[0], g[1] / g[2]) for g in groups]
    verts = []
    for i in range(len(coords)):
        o1, c1 = coords[i]
        o2, c2 = coords[(i + 1) % len(coords)]
        verts.append((c1, c2) if o1 == "V" else (c2, c1))  # vertex = (x from V edge, y from H edge)
    return verts


def room_polygon(poly, tol):
    """Orthogonal polygon (<= MAX_VERTS vertices) approximating poly; bbox as last resort."""
    for mult in (1, 2, 4, 8):
        verts = orthogonalize(poly, tol * mult)
        if verts is None or len(verts) > MAX_VERTS:
            continue
        q = Polygon(verts)
        if q.is_valid and 0.7 * poly.area <= q.area <= 1.3 * poly.area:
            return verts, "ortho"
    minx, miny, maxx, maxy = poly.bounds
    return [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)], "bbox"


def cluster_map(values, tol):
    order = sorted(set(values))
    groups = []
    for v in order:
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    mapping = {}
    for g in groups:
        m = int(round(sum(g) / len(g)))
        for v in g:
            mapping[v] = m
    return mapping


def clean_ring(ring):
    """Drop repeated and collinear vertices of an integer ring."""
    changed = True
    while changed and len(ring) >= 3:
        changed = False
        out = []
        n = len(ring)
        for i in range(n):
            prev, cur, nxt = ring[i - 1], ring[i], ring[(i + 1) % n]
            if cur == prev:
                changed = True
                continue
            cross = (cur[0] - prev[0]) * (nxt[1] - cur[1]) - (cur[1] - prev[1]) * (nxt[0] - cur[0])
            if cross == 0:
                changed = True
                continue
            out.append(cur)
        ring = out
    return ring


def on_segment(q, a, b):
    if a[0] == b[0] == q[0]:
        return min(a[1], b[1]) < q[1] < max(a[1], b[1])
    if a[1] == b[1] == q[1]:
        return min(a[0], b[0]) < q[0] < max(a[0], b[0])
    return False


def seg_project(c, a, b):
    """Distance from point c to segment a-b and the distance of the projection from a."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    t = ((c[0] - ax) * dx + (c[1] - ay) * dy) / (length * length)
    t = max(0.0, min(1.0, t))
    px, py = ax + t * dx, ay + t * dy
    return math.hypot(c[0] - px, c[1] - py), t * length, length


# --------------------------------------------------------------------- conversion
def convert_plan(svg_path, png_path, plan_id="plan"):
    root = ET.parse(svg_path).getroot()
    W, H = Image.open(png_path).size
    sw = numbers(root.get("width", ""))
    sh = numbers(root.get("height", ""))
    if not (sw and sh):
        vb = numbers(root.get("viewBox", ""))
        sw, sh = ([vb[2]], [vb[3]]) if len(vb) == 4 else ([W], [H])
    k = GRID / max(W, H)
    fx, fy = (W / sw[0]) * k, (H / sh[0]) * k

    def to_grid(p):
        return affinity.scale(p, fx, fy, origin=(0, 0))

    items = collect(root)
    thick = wall_thickness(items["Wall"]) * (fx + fy) / 2  # in grid units
    simp_tol = max(3.0, 0.5 * thick)
    snap_tol = max(4.0, 0.8 * thick)

    # rooms -> orthogonal polygons
    raw = []  # (type, orig polygon, verts, method)
    for el in items["Space"]:
        cls = (el.get("class") or "").split()
        name = " ".join(cls[1:])
        if any(s in name.lower() for s in SKIP_ROOMS):
            continue
        polys = polygons_in(el)
        if not polys:
            continue
        orig = to_grid(max(polys, key=lambda g: g.area))
        if orig.area < 30:
            continue
        grown = orig.buffer(thick / 2, join_style=2)
        if grown.geom_type == "MultiPolygon":
            grown = max(grown.geoms, key=lambda g: g.area)
        verts, method = room_polygon(grown, simp_tol)
        raw.append((room_type(name), orig, verts, method))
    if not raw:
        raise ValueError("no rooms found")

    # snap to a shared grid
    xs = [v[0] for _, _, vs, _ in raw for v in vs]
    ys = [v[1] for _, _, vs, _ in raw for v in vs]
    mx = cluster_map([int(round(x)) for x in xs], snap_tol)
    my = cluster_map([int(round(y)) for y in ys], snap_tol)
    rooms_in = []
    for rtype, orig, verts, method in raw:
        ring = [
            (min(max(mx[int(round(x))], 0), GRID), min(max(my[int(round(y))], 0), GRID))
            for x, y in verts
        ]
        ring = clean_ring(ring)
        if len(ring) < 4:
            continue
        q = Polygon(ring)
        if not q.is_valid or q.area < 20:
            continue
        rooms_in.append((rtype, orig, ring, method))
    if not rooms_in:
        raise ValueError("no valid rooms after snapping")

    # wall graph
    all_pts = {p for _, _, ring, _ in rooms_in for p in ring}
    vert_ids, vertices = {}, []

    def vid(p):
        if p not in vert_ids:
            vert_ids[p] = len(vertices)
            vertices.append(list(p))
        return vert_ids[p]

    wall_key, walls = {}, []
    rooms = []
    for ri, (rtype, orig, ring, method) in enumerate(rooms_in):
        loop = []
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            pts = [q for q in all_pts if on_segment(q, a, b)]
            pts = sorted([a, b] + pts, key=lambda q: (q[0] - a[0]) ** 2 + (q[1] - a[1]) ** 2)
            for u, v in zip(pts, pts[1:]):
                key = frozenset((u, v))
                if key not in wall_key:
                    wall_key[key] = len(walls)
                    walls.append({"id": len(walls), "a": vid(u), "b": vid(v), "cls": "interior",
                                  "thickness": round(thick, 1)})
                loop.append(wall_key[key])
        rooms.append({
            "id": ri, "type": rtype, "method": method,
            "polygon": [list(p) for p in ring],
            "loop": loop,
            "orig_polygon": [[round(x, 1), round(y, 1)] for x, y in orig.exterior.coords][:-1],
        })

    outline = unary_union([Polygon(r["polygon"]) for r in rooms]).buffer(0).boundary
    for w in walls:
        a, b = vertices[w["a"]], vertices[w["b"]]
        mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if outline.distance(mid) <= 1.5:
            w["cls"] = "exterior"

    # openings
    openings, dropped = [], 0
    for kind in ("Door", "Window"):
        for el in items[kind]:
            polys = []
            for sub in el.iter():
                sid = ((sub.get("id") or "") + " " + (sub.get("class") or "")).lower()
                if "threshold" in sid:
                    polys += polygons_in(sub)
            if not polys:
                polys = polygons_in(el)
            if not polys:
                continue
            g = to_grid(unary_union(polys))
            minx, miny, maxx, maxy = g.bounds
            c = ((minx + maxx) / 2, (miny + maxy) / 2)
            major = max(maxx - minx, maxy - miny)
            best = None
            for w in walls:
                a, b = vertices[w["a"]], vertices[w["b"]]
                d, along, length = seg_project(c, a, b)
                if best is None or d < best[0]:
                    best = (d, w["id"], along, length)
            if best is None or best[0] > max(4 * thick, 20):
                dropped += 1
                continue
            _, wid, along, length = best
            width = min(major, length)
            start = min(max(along - width / 2, 0.0), length - width)
            openings.append({"id": len(openings), "kind": kind.lower(), "wall": wid,
                             "offset": round(start, 1), "width": round(width, 1),
                             "sill": 0.9 if kind == "Window" else 0.0,
                             "height": 1.2 if kind == "Window" else 2.1})

    return {
        "plan_id": plan_id, "image_size": [W, H], "grid": GRID,
        "wall_thickness": round(thick, 1), "dropped_openings": dropped,
        "vertices": vertices, "walls": walls, "rooms": rooms, "openings": openings,
    }


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="folder containing train.txt / val.txt / test.txt")
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    root = Path(args.root)
    lines = [l.strip().strip("/") for l in (root / f"{args.split}.txt").read_text().splitlines() if l.strip()]
    if args.limit:
        lines = lines[: args.limit]
    out = Path(args.out) / args.split
    out.mkdir(parents=True, exist_ok=True)

    ok, failures = 0, {}
    for rel in lines:
        plan_id = rel.replace("/", "_")
        folder = root / rel
        try:
            res = convert_plan(folder / "model.svg", folder / "F1_scaled.png", plan_id)
            (out / f"{plan_id}.json").write_text(json.dumps(res))
            shutil.copy(folder / "F1_scaled.png", out / f"{plan_id}.png")
            ok += 1
        except Exception as e:  # keep going, report at the end
            failures[plan_id] = f"{type(e).__name__}: {e}"
            if len(failures) <= 3:
                traceback.print_exc()
    (out / "_failures.json").write_text(json.dumps(failures, indent=1))
    print(f"converted {ok}/{len(lines)} plans -> {out}  (failures: {len(failures)})")


if __name__ == "__main__":
    main()