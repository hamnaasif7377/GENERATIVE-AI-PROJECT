#!/usr/bin/env python
"""Verify converted CubiCasa5K plans (output of convert_cubicasa.py).

Checks, per plan:
  * room IoU: converted room masks vs the original CubiCasa room polygons (mean over rooms)
  * validity: closed room loops, valid polygons, small room overlap, openings fully inside one wall
    and not overlapping each other
Plans with mean IoU < --thresh or that fail validity are excluded. The script writes:
  <data>/verified.txt                      ids of kept plans (the test set is drawn only from these)
  <out>/conversion_report_<split>.json     per-plan numbers, exclusion share, failure reasons
  <out>/manual_check/*.png + manual_check.csv   50 random kept plans to compare by eye (both members)

Usage:
  python scripts/verify_conversion.py --data data/processed/test --out results
"""
import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

R = 512  # mask resolution


def mask(poly, grid):
    m = np.zeros((R, R), np.uint8)
    pts = np.round(np.array(poly, dtype=float) * R / grid).astype(np.int32)
    cv2.fillPoly(m, [pts], 1)
    return m


def iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def loop_closed(room, walls):
    ends = [(walls[w]["a"], walls[w]["b"]) for w in room["loop"]]
    deg = Counter(v for e in ends for v in e)
    if any(c != 2 for c in deg.values()):
        return False
    adj = {}
    for a, b in ends:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, stack = set(), [ends[0][0]]
    while stack:
        v = stack.pop()
        if v not in seen:
            seen.add(v)
            stack.extend(adj[v])
    return len(seen) == len(deg)


def wall_len(w, verts):
    a, b = verts[w["a"]], verts[w["b"]]
    return abs(a[0] - b[0]) + abs(a[1] - b[1])  # walls are axis-aligned


def check_plan(d):
    """Return (mean room IoU, list of failure reasons)."""
    g = d["grid"]
    walls = {w["id"]: w for w in d["walls"]}
    verts = d["vertices"]
    reasons = []

    ious = []
    for r in d["rooms"]:
        ious.append(iou(mask(r["polygon"], g), mask(r["orig_polygon"], g)))
    mean_iou = float(np.mean(ious)) if ious else 0.0

    polys = [Polygon(r["polygon"]) for r in d["rooms"]]
    if any((not p.is_valid) or p.area <= 0 for p in polys):
        reasons.append("invalid_polygon")
    if not all(loop_closed(r, walls) for r in d["rooms"]):
        reasons.append("open_loop")
    union = unary_union([p.buffer(0) for p in polys]).area
    if union > 0 and (sum(p.area for p in polys) - union) / union > 0.03:
        reasons.append("room_overlap")

    by_wall = {}
    for o in d["openings"]:
        w = walls.get(o["wall"])
        if w is None:
            reasons.append("opening_missing_wall")
            continue
        L = wall_len(w, verts)
        if o["offset"] < -1e-6 or o["offset"] + o["width"] > L + 1e-6:
            reasons.append("opening_outside_wall")
        by_wall.setdefault(o["wall"], []).append((o["offset"], o["offset"] + o["width"]))
    for spans in by_wall.values():
        spans.sort()
        if any(s2[0] < s1[1] - 1e-6 for s1, s2 in zip(spans, spans[1:])):
            reasons.append("opening_overlap")
            break
    return mean_iou, sorted(set(reasons))


def overlay(d, img_path, out_path):
    img = cv2.imread(str(img_path))
    if img is None:
        return
    s = max(img.shape[:2]) / d["grid"]
    for r in d["rooms"]:
        cv2.polylines(img, [np.round(np.array(r["polygon"]) * s).astype(np.int32)], True, (0, 160, 0), 2)
        cv2.polylines(img, [np.round(np.array(r["orig_polygon"]) * s).astype(np.int32)], True, (0, 0, 220), 1)
        c = np.round(np.mean(r["polygon"], axis=0) * s).astype(int)
        cv2.putText(img, r["type"], tuple(c), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 0, 0), 1)
    walls = {w["id"]: w for w in d["walls"]}
    for o in d["openings"]:
        w = walls[o["wall"]]
        a = np.array(d["vertices"][w["a"]], float)
        b = np.array(d["vertices"][w["b"]], float)
        u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        p1, p2 = a + u * o["offset"], a + u * (o["offset"] + o["width"])
        col = (255, 0, 0) if o["kind"] == "door" else (0, 200, 255)
        cv2.line(img, tuple(np.round(p1 * s).astype(int)), tuple(np.round(p2 * s).astype(int)), col, 4)
    cv2.imwrite(str(out_path), img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder with converted <id>.json and <id>.png")
    ap.add_argument("--out", default="results")
    ap.add_argument("--thresh", type=float, default=0.85)
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data = Path(args.data)
    split = data.name
    files = sorted(p for p in data.glob("*.json") if not p.name.startswith("_"))
    per_plan, kept = {}, []
    reason_count = Counter()
    for f in files:
        d = json.loads(f.read_text())
        m_iou, reasons = check_plan(d)
        low = m_iou < args.thresh
        if low:
            reasons = reasons + ["low_iou"]
        per_plan[f.stem] = {"mean_iou": round(m_iou, 4), "reasons": reasons}
        reason_count.update(reasons)
        if not reasons:
            kept.append(f.stem)

    n = len(files)
    report = {
        "split": split, "converted": n, "kept": len(kept), "excluded": n - len(kept),
        "excluded_share": round((n - len(kept)) / n, 4) if n else None,
        "mean_iou_all": round(float(np.mean([v["mean_iou"] for v in per_plan.values()])), 4) if n else None,
        "mean_iou_kept": round(float(np.mean([per_plan[k]["mean_iou"] for k in kept])), 4) if kept else None,
        "failure_reasons": dict(reason_count), "plans": per_plan,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"conversion_report_{split}.json").write_text(json.dumps(report, indent=1))
    (data / "verified.txt").write_text("\n".join(kept))

    # manual check sample
    sample = random.Random(args.seed).sample(kept, min(args.sample, len(kept)))
    mc = out / "manual_check"
    mc.mkdir(exist_ok=True)
    for pid in sample:
        overlay(json.loads((data / f"{pid}.json").read_text()), data / f"{pid}.png", mc / f"{pid}.png")
    with open(out / "manual_check.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["plan_id", "merged_rooms", "shifted_openings", "lost_walls", "other", "notes"])
        for pid in sample:
            w.writerow([pid, 0, 0, 0, 0, ""])

    print(f"{split}: converted={n} kept={len(kept)} excluded={n - len(kept)} "
          f"({report['excluded_share']}) mean IoU kept={report['mean_iou_kept']}")
    print("failure reasons:", dict(reason_count))
    print(f"manual check: {len(sample)} overlays in {mc}, fill {out / 'manual_check.csv'}")


if __name__ == "__main__":
    main()