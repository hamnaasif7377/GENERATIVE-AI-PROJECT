#!/usr/bin/env python3
"""Build a static gallery page for the generated glTF scenes.

Reads the layout JSONs in data/processed/test (for metadata) and the matching
.glb / .png files in results/3d, then writes frontend/gallery.html.

Usage:
  python scripts/make_gallery.py [--plans DIR] [--scenes DIR] [--out FILE]
"""

import argparse
import html
import json
from collections import Counter
from pathlib import Path

from shapely.geometry import Polygon

TYPE_LABEL = {
    "living_room": "Living",
    "kitchen": "Kitchen",
    "bedroom": "Bedroom",
    "bathroom": "Bath",
    "hall": "Hall",
    "other": "Other",
}


def describe(plan_path, scene_path, plan_width=15.0):
    plan = json.loads(plan_path.read_text())
    grid = plan.get("grid", 1000)
    scale = plan_width / grid
    area = 0.0
    for room in plan.get("rooms", []):
        try:
            poly = Polygon([(x * scale, y * scale) for x, y in room["polygon"]])
            if poly.is_valid:
                area += poly.area
        except Exception:
            pass
    types = Counter(r.get("type", "other") for r in plan.get("rooms", []))
    return {
        "id": plan_path.stem,
        "rooms": len(plan.get("rooms", [])),
        "walls": len(plan.get("walls", [])),
        "openings": len(plan.get("openings", [])),
        "area": area,
        "types": types,
        "glb": scene_path.name,
        "png": scene_path.with_suffix(".png").name,
    }


def type_chips(types):
    chips = []
    for key, label in TYPE_LABEL.items():
        n = types.get(key, 0)
        if n:
            suffix = f" ×{n}" if n > 1 else ""
            chips.append(f'<span class="chip {key}">{label}{suffix}</span>')
    return "".join(chips)


def card(item, featured=False):
    png = f"../results/3d/{item['png']}"
    glb = f"../results/3d/{item['glb']}"
    link = f"viewer.html?model={glb}"
    cls = "card featured" if featured else "card"
    extra = (
        '<div class="shots">'
        f'<a href="{link}"><img src="{png}" alt="{html.escape(item["id"])} exterior"></a>'
        '<a href="' + link + '&cam=2.6,1.65,4.6&look=9.5,1.3,7.6&grid=0&bg=dfe9f2">'
        '<img src="../results/3d/high_quality_architectural_22_interior.png" alt="interior"></a>'
        "</div>"
        if featured
        else f'<a href="{link}"><img src="{png}" alt="{html.escape(item["id"])}"></a>'
    )
    return f"""
    <article class="{cls}">
      {extra}
      <div class="meta">
        <h3>{html.escape(item['id'])}</h3>
        <p class="stats">{item['rooms']} rooms · {item['walls']} walls ·
           {item['openings']} openings · {item['area']:.0f} m²</p>
        <div class="chips">{type_chips(item['types'])}</div>
        <a class="open" href="{link}">Open 3D walkthrough →</a>
      </div>
    </article>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", default="data/processed/test")
    ap.add_argument("--scenes", default="results/3d")
    ap.add_argument("--out", default="frontend/gallery.html")
    args = ap.parse_args()

    plans_dir = Path(args.plans)
    scenes_dir = Path(args.scenes)
    items = []
    for glb in sorted(scenes_dir.glob("*.glb")):
        plan_path = plans_dir / f"{glb.stem}.json"
        if not plan_path.exists():
            continue
        items.append(describe(plan_path, glb))
    if not items:
        raise SystemExit("no matching plan/scene pairs found")
    items.sort(key=lambda i: (i["rooms"], i["id"]))

    demo = next((i for i in items if i["id"] == "high_quality_architectural_22"), items[0])
    rest = [i for i in items if i is not demo]
    total_rooms = sum(i["rooms"] for i in items)
    total_area = sum(i["area"] for i in items)

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plan2Walk · 3D gallery</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background: #0b1016; color: #dfe8f2; }}
  header {{ max-width: 1180px; margin: 0 auto; padding: 56px 24px 24px; }}
  header h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: -0.02em; }}
  header p {{ margin: 0; color: #93a4b8; max-width: 760px; line-height: 1.6; }}
  .kpis {{ display: flex; gap: 28px; margin-top: 22px; flex-wrap: wrap; }}
  .kpi b {{ display: block; font-size: 24px; color: #fff; }}
  .kpi span {{ font-size: 12px; color: #8b9bb0; text-transform: uppercase; letter-spacing: .08em; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 8px 24px 72px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 22px; }}
  .card {{ background: #121a23; border: 1px solid #223040; border-radius: 16px; overflow: hidden;
           display: flex; flex-direction: column; }}
  .card img {{ display: block; width: 100%; aspect-ratio: 18/13; object-fit: cover; background: #0b1016; }}
  .card.featured {{ grid-column: 1 / -1; }}
  .card.featured .shots {{ display: grid; grid-template-columns: 1fr 1fr; }}
  .card.featured .shots img {{ aspect-ratio: 18/11; }}
  .meta {{ padding: 16px 18px 18px; display: flex; flex-direction: column; gap: 8px; }}
  .meta h3 {{ margin: 0; font-size: 15px; font-weight: 600; letter-spacing: .01em; }}
  .stats {{ margin: 0; color: #8b9bb0; font-size: 12px; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{ font-size: 11px; padding: 3px 8px; border-radius: 999px; background: #1b2734;
           border: 1px solid #2b3b4d; color: #b9c7d6; }}
  .chip.living_room {{ border-color: #3f6f5a; }}
  .chip.kitchen {{ border-color: #6f5c33; }}
  .chip.bedroom {{ border-color: #3d5a7a; }}
  .chip.bathroom {{ border-color: #4a6f78; }}
  .open {{ margin-top: 4px; color: #7cc4ff; text-decoration: none; font-size: 13px; font-weight: 600; }}
  .open:hover {{ text-decoration: underline; }}
  .note {{ margin: 28px 0 34px; padding: 16px 18px; border-radius: 12px; background: #101820;
           border: 1px solid #1f2c3a; color: #93a4b8; font-size: 13px; line-height: 1.6; }}
  code {{ background: #0d1319; padding: 2px 6px; border-radius: 5px; color: #93c5fd; }}
</style>
</head>
<body>
<header>
  <h1>Plan2Walk · 3D gallery</h1>
  <p>Deterministic glTF scenes built from converted CubiCasa5K floor plans. Each scene is a
     wall graph with cut openings, door and window frames, floors and a single ceiling.
     Open one to orbit it, then click <b>Walk</b> for first-person movement (WASD, mouse look).</p>
  <div class="kpis">
    <div class="kpi"><b>{len(items)}</b><span>3D scenes</span></div>
    <div class="kpi"><b>{total_rooms}</b><span>rooms</span></div>
    <div class="kpi"><b>{total_area:.0f}</b><span>m² modelled</span></div>
    <div class="kpi"><b>0.03–0.18</b><span>MB per GLB</span></div>
  </div>
</header>
<main>
  <div class="grid">{card(demo, featured=True)}
{''.join(card(i) for i in rest)}
  </div>
  <div class="note">
    Rebuild any scene with
    <code>python scripts/build_scene.py --plan data/processed/test/&lt;id&gt;.json --out results/3d/&lt;id&gt;.glb</code>,
    or rebuild the whole gallery with
    <code>python scripts/build_scene.py --data data/processed/test --out results/3d --only ...</code>
    then <code>python scripts/make_gallery.py</code>.
    Interior screenshot camera parameters are reproducible through the viewer URL:
    <code>cam=</code>, <code>look=</code>, <code>still=1</code>, <code>hud=0</code>, <code>grid=0</code>.
  </div>
</main>
</body>
</html>
"""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"wrote {out} with {len(items)} scenes ({total_rooms} rooms, {total_area:.0f} m²)")


if __name__ == "__main__":
    main()
