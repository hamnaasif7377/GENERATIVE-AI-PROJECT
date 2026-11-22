#!/usr/bin/env python
"""Build a 3D GLB scene from a converted Plan2Walk layout JSON.

The layout JSON stores an orthogonal wall graph in grid units (0..1000).
This script turns it into metre-scale geometry:

  * walls are boxes centred on the wall graph (exterior walls are shifted out
    so their inner face sits on the room boundary)
  * door and window openings are cut by splitting each wall into solid pieces
    plus a lintel (and a sill below windows)
  * windows get a thin translucent pane
  * every room gets a floor slab, and optionally a translucent ceiling

Usage:
  python scripts/build_scene.py \
      --plan data/processed/test/high_quality_architectural_22.json \
      --out results/3d/high_quality_architectural_22.glb \
      --plan-width 15
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from trimesh.transformations import rotation_matrix, translation_matrix
from trimesh.visual.material import PBRMaterial


def material(rgba, metallic=0.0, roughness=0.9, alpha=False):
    return PBRMaterial(
        baseColorFactor=rgba,
        metallicFactor=metallic,
        roughnessFactor=roughness,
        alphaMode="BLEND" if alpha else "OPAQUE",
        doubleSided=alpha,
    )


WALL = material([0.84, 0.83, 0.80, 1.0], roughness=0.95)
FLOOR = material([0.56, 0.41, 0.27, 1.0], roughness=0.85)
CEILING = material([0.96, 0.96, 0.95, 1.0], roughness=0.95)
GLASS = material([0.52, 0.76, 0.95, 0.30], metallic=0.0, roughness=0.08, alpha=True)
DOOR = material([0.42, 0.28, 0.16, 1.0], roughness=0.8)


def box(length, height, thickness, center, angle, mat, name):
    """A box whose local x runs along the wall and local y is vertical."""
    mesh = trimesh.creation.box(extents=(max(length, 1e-4), max(height, 1e-4), max(thickness, 1e-4)))
    transform = translation_matrix(center) @ rotation_matrix(angle, [0, 1, 0])
    mesh.apply_transform(transform)
    mesh.visual = trimesh.visual.TextureVisuals(material=mat)
    mesh.metadata["name"] = name
    return mesh


def wall_angle(a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    return math.atan2(-dz, dx)


def build(plan, plan_width=15.0, wall_height=2.7, floor_thickness=0.05, ceilings=True, windows=True):
    grid = plan.get("grid", 1000)
    scale = plan_width / grid
    rooms = plan.get("rooms", [])
    walls = {w["id"]: w for w in plan.get("walls", [])}
    vertices = plan["vertices"]

    # room footprint in metres, used to decide which side of an exterior wall is outside
    footprints = []
    for r in rooms:
        try:
            p = Polygon(r["polygon"])
            if p.is_valid and p.area > 0:
                footprints.append(p)
        except Exception:
            pass
    outline = unary_union(footprints) if footprints else None

    openings_by_wall = {}
    for o in plan.get("openings", []):
        openings_by_wall.setdefault(o["wall"], []).append(o)

    meshes = []
    for wid, w in walls.items():
        a = (vertices[w["a"]][0] * scale, vertices[w["a"]][1] * scale)
        b = (vertices[w["b"]][0] * scale, vertices[w["b"]][1] * scale)
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dz)
        if length < 1e-4:
            continue
        ux, uz = dx / length, dz / length
        nx, nz = -uz, ux  # left normal in the XZ plane
        thickness = max(w.get("thickness") or plan.get("wall_thickness", 6.0), 1.0) * scale
        thickness = min(max(thickness, 0.10), 0.40)

        # shift exterior walls outward so the room side stays on the room boundary
        shift = 0.0
        if w.get("cls") == "exterior" and outline is not None:
            mx = (a[0] + b[0]) / 2 + nx * (thickness / 2 + 0.05)
            mz = (a[1] + b[1]) / 2 + nz * (thickness / 2 + 0.05)
            if not outline.buffer(0.01).contains(Point(mx / scale, mz / scale)):
                shift = thickness / 2
            else:
                shift = -thickness / 2

        base_x = a[0] + nx * shift
        base_z = a[1] + nz * shift
        angle = wall_angle(a, b)

        def centre(off, height_mid):
            return (base_x + ux * off, height_mid, base_z + uz * off)

        ops = sorted(openings_by_wall.get(wid, []), key=lambda o: o["offset"])
        cuts = []
        for o in ops:
            start = max(0.0, o["offset"] * scale)
            end = min(length, (o["offset"] + o["width"]) * scale)
            if end <= start:
                continue
            sill = float(o.get("sill", 0.0))
            height = float(o.get("height", 2.1))
            top = min(wall_height, sill + height)
            cuts.append((start, end, sill, top, o))

        # full-height pieces between openings
        cursor = 0.0
        for start, end, _, _, _ in cuts:
            if start > cursor + 1e-4:
                seg = start - cursor
                meshes.append(box(seg, wall_height, thickness, centre((cursor + start) / 2, wall_height / 2), angle,
                                  WALL, f"Wall_{wid}_solid"))
            cursor = max(cursor, end)
        if cursor < length - 1e-4:
            seg = length - cursor
            meshes.append(box(seg, wall_height, thickness, centre((cursor + length) / 2, wall_height / 2), angle,
                              WALL, f"Wall_{wid}_solid"))

        # lintels, sills and glazing
        for start, end, sill, top, o in cuts:
            width = end - start
            if top < wall_height - 1e-4:
                h = wall_height - top
                meshes.append(box(width, h, thickness, centre((start + end) / 2, top + h / 2), angle,
                                  WALL, f"Wall_{wid}_lintel"))
            if sill > 1e-4:
                meshes.append(box(width, sill, thickness, centre((start + end) / 2, sill / 2), angle,
                                  WALL, f"Wall_{wid}_sill"))
            if windows and o.get("kind") == "window":
                pane_t = min(0.03, thickness * 0.5)
                pane_h = max(top - sill, 0.05)
                frame_t = max(pane_t * 1.8, 0.055)
                mid_off = (start + end) / 2
                mid_h = (sill + top) / 2
                meshes.append(box(width * 0.96, pane_h * 0.98, pane_t,
                                  centre(mid_off, mid_h), angle,
                                  GLASS, f"Window_{o['id']}"))
                # white frame and mullion make the glazing read as a window
                meshes.append(box(0.04, pane_h, frame_t,
                                  centre(mid_off, mid_h), angle,
                                  WALL, f"Window_{o['id']}_mullion"))
                meshes.append(box(width, 0.05, frame_t,
                                  centre(mid_off, sill + 0.025), angle,
                                  WALL, f"Window_{o['id']}_rail"))
                meshes.append(box(width, 0.05, frame_t,
                                  centre(mid_off, top - 0.025), angle,
                                  WALL, f"Window_{o['id']}_rail"))
                meshes.append(box(0.05, pane_h, frame_t,
                                  centre(start + 0.025, mid_h), angle,
                                  WALL, f"Window_{o['id']}_jamb"))
                meshes.append(box(0.05, pane_h, frame_t,
                                  centre(end - 0.025, mid_h), angle,
                                  WALL, f"Window_{o['id']}_jamb"))
            elif o.get("kind") == "door":
                # threshold, jambs and header: reads as a door from above and inside
                frame_t = thickness * 1.06
                meshes.append(box(width, 0.02, thickness * 0.9,
                                  centre((start + end) / 2, 0.01), angle,
                                  DOOR, f"Door_{o['id']}"))
                meshes.append(box(0.07, top, frame_t,
                                  centre(start + 0.035, top / 2), angle,
                                  DOOR, f"Door_{o['id']}_jamb"))
                meshes.append(box(0.07, top, frame_t,
                                  centre(end - 0.035, top / 2), angle,
                                  DOOR, f"Door_{o['id']}_jamb"))
                meshes.append(box(max(width - 0.14, 0.05), 0.08, frame_t,
                                  centre((start + end) / 2, top - 0.04), angle,
                                  DOOR, f"Door_{o['id']}_header"))

    # floors and ceilings
    for r in rooms:
        try:
            poly = Polygon([(x * scale, y * scale) for x, y in r["polygon"]])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.area < 1e-4:
                continue
            floor = trimesh.creation.extrude_polygon(poly, floor_thickness)
            floor.apply_transform(rotation_matrix(math.pi / 2, [1, 0, 0]))
            floor.visual = trimesh.visual.TextureVisuals(material=FLOOR)
            floor.metadata["name"] = f"Floor_{r['id']}_{r['type']}"
            meshes.append(floor)
        except Exception:
            continue

    # one ceiling over the whole building outline: covers room interiors and wall tops,
    # so no sky shows through the joints between rooms
    if ceilings and outline is not None:
        cap = outline.buffer(max(2.0, plan.get("wall_thickness", 6.0)), join_style=2)
        caps = [cap] if cap.geom_type == "Polygon" else [g for g in getattr(cap, "geoms", []) if g.geom_type == "Polygon"]
        for i, c in enumerate(caps):
            try:
                poly = Polygon([(x * scale, y * scale) for x, y in c.exterior.coords])
                if poly.is_empty or poly.area < 1e-4:
                    continue
                v2, faces = trimesh.creation.triangulate_polygon(poly)
                verts = np.column_stack([v2[:, 0], np.full(len(v2), wall_height), v2[:, 1]])
                ceil = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
                if ceil.face_normals[:, 1].mean() > 0:  # make sure the visible side faces down
                    ceil.invert()
                ceil.visual = trimesh.visual.TextureVisuals(material=CEILING)
                ceil.metadata["name"] = "Ceiling_building" if i == 0 else f"Ceiling_building_{i}"
                meshes.append(ceil)
            except Exception:
                continue

    scene = trimesh.Scene()
    for m in meshes:
        scene.add_geometry(m, geom_name=m.metadata.get("name", "mesh"), node_name=m.metadata.get("name", "mesh"))
    return scene


def build_one(plan_path, out_path, args):
    plan = json.loads(Path(plan_path).read_text())
    scene = build(plan, args.plan_width, args.wall_height, args.floor_thickness,
                  ceilings=not args.no_ceiling, windows=not args.no_windows)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(out, file_type="glb")
    bounds = scene.bounds
    print(f"{plan['plan_id']}: {len(scene.geometry)} meshes, "
          f"{len(plan.get('walls', []))} walls, {len(plan.get('rooms', []))} rooms, "
          f"{len(plan.get('openings', []))} openings -> {out.name} "
          f"({out.stat().st_size / 1e6:.2f} MB, "
          f"{np.round(bounds[1] - bounds[0], 1).tolist()} m)")
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", help="one layout JSON, or a directory of them")
    ap.add_argument("--data", help="directory of layout JSONs (batch mode)")
    ap.add_argument("--out", required=True, help="output .glb or output directory in batch mode")
    ap.add_argument("--only", help="comma-separated plan ids to build (batch mode)")
    ap.add_argument("--limit", type=int, help="maximum number of plans in batch mode")
    ap.add_argument("--plan-width", type=float, default=15.0, help="longer plan side in metres")
    ap.add_argument("--wall-height", type=float, default=2.7)
    ap.add_argument("--floor-thickness", type=float, default=0.05)
    ap.add_argument("--no-ceiling", action="store_true")
    ap.add_argument("--no-windows", action="store_true")
    args = ap.parse_args()

    src = Path(args.data or args.plan or "")
    if not src.exists():
        ap.error("pass --plan or --data")

    if src.is_dir():
        files = sorted(p for p in src.glob("*.json") if not p.name.startswith("_"))
        if args.only:
            wanted = {s.strip() for s in args.only.split(",") if s.strip()}
            files = [p for p in files if p.stem in wanted]
        if args.limit:
            files = files[: args.limit]
        if not files:
            ap.error(f"no layout JSON files found in {src}")
        out_dir = Path(args.out)
        built = 0
        for f in files:
            try:
                build_one(f, out_dir / f"{f.stem}.glb", args)
                built += 1
            except Exception as e:
                print(f"{f.stem}: FAILED {type(e).__name__}: {e}")
        print(f"built {built}/{len(files)} scenes -> {out_dir}")
    else:
        build_one(src, args.out, args)


if __name__ == "__main__":
    main()
