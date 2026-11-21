"""Synthetic check of the CubiCasa converter: two rooms separated by a wall, one door on it."""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from convert_cubicasa import convert_plan  # noqa: E402
from verify_conversion import check_plan  # noqa: E402

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
<g id="Model">
 <g class="Wall"><polygon points="20,20 380,20 380,30 20,30"/></g>
 <g class="Wall"><polygon points="20,270 380,270 380,280 20,280"/></g>
 <g class="Wall"><polygon points="195,30 205,30 205,270 195,270"/>
  <g class="Door Swing Beside"><g id="Threshold"><polygon points="193,120 207,120 207,160 193,160"/></g></g>
 </g>
 <g class="Space Bedroom"><polygon points="30,30 195,30 195,270 30,270"/></g>
 <g class="Space Kitchen"><polygon points="205,30 370,30 370,270 205,270"/></g>
</g></svg>"""


def test_two_rooms_share_wall(tmp_path):
    svg, png = tmp_path / "model.svg", tmp_path / "F1_scaled.png"
    svg.write_text(SVG)
    Image.new("RGB", (400, 300), "white").save(png)

    d = convert_plan(svg, png, "synthetic")
    assert len(d["rooms"]) == 2
    assert {r["type"] for r in d["rooms"]} == {"bedroom", "kitchen"}

    shared = set(d["rooms"][0]["loop"]) & set(d["rooms"][1]["loop"])
    assert shared, "neighbouring rooms must reference a common wall"

    assert len(d["openings"]) == 1
    assert d["openings"][0]["kind"] == "door"
    assert d["openings"][0]["wall"] in shared

    mean_iou, reasons = check_plan(d)
    assert reasons == []
    assert mean_iou > 0.85