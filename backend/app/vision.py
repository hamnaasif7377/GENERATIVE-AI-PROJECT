"""F2: uploaded plan image (PNG/JPG/PDF) -> layout, read by a vision model."""

from __future__ import annotations

import base64
import io
import math
import re

from PIL import Image

from .genai import GenAIError, get_provider
from .layout import new_plan_id, normalise_type
from .packing import normalise_program, program_to_layout
from .validator import validate

VISION_PROMPT = """You are Plan2Walk's floor-plan reader. Read the uploaded floor plan image and return ONLY JSON:
{
  "title": "short title",
  "plot_aspect": 1.2,
  "plot_width_m": 12.0,
  "rooms": [
    {"name": "Kitchen", "type": "kitchen", "bbox": [0.05, 0.10, 0.35, 0.45], "windows": 1, "doors": 1}
  ],
  "entrance": "Hall",
  "notes": "one sentence about what is legible"
}

Rules:
- bbox is [x0, y0, x1, y1] in normalized image coordinates (0..1, x right, y down).
- Use the room labels written on the drawing. Include every enclosed room once.
- type is one of: living_room, kitchen, bedroom, bathroom, hall, other.
- windows/doors are counts you can see for that room (0 if none).
- plot_aspect is plot width divided by depth. plot_width_m is only set if a dimension is legible, otherwise null.
- Do not invent rooms that are not in the drawing.
"""


class VisionError(RuntimeError):
    pass


def image_to_png(data: bytes, filename: str = "") -> tuple[bytes, int, int]:
    """Normalise an upload to PNG. PDFs are rendered on page 1."""
    if data[:4] == b"%PDF" or filename.lower().endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:  # pragma: no cover
            raise VisionError("PDF support needs PyMuPDF (pip install pymupdf)") from exc
        document = fitz.open(stream=data, filetype="pdf")
        if document.page_count == 0:
            raise VisionError("the PDF has no pages")
        page = document.load_page(0)
        pixmap = page.get_pixmap(dpi=150, alpha=False)
        png = pixmap.tobytes("png")
        image = Image.open(io.BytesIO(png)).convert("RGB")
    else:
        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise VisionError("could not read the image (use PNG, JPG or PDF)") from exc

    if max(image.size) > 1400:
        scale = 1400 / max(image.size)
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), image.width, image.height


def _norm_bbox(raw, width: int, height: int) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        values = [float(v) for v in raw[:4]]
    except (TypeError, ValueError):
        return None
    if max(values) > 1.5:
        values = [values[0] / width, values[1] / height, values[2] / width, values[3] / height]
    x0, y0, x1, y1 = values
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    # Some models return [x, y, w, h]; convert when it looks like a size.
    if x1 <= 1.0 and y1 <= 1.0 and x1 > 0 and y1 > 0 and (x1 < x0 + 0.05 or y1 < y0 + 0.05):
        x1, y1 = x0 + x1, y0 + y1
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(1.0, x1), min(1.0, y1)
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        return None
    return x0, y0, x1, y1


def _zone_for(x0: float, y0: float, x1: float, y1: float) -> str:
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    if cy < 0.38:
        return "back"
    if cy > 0.62:
        return "front"
    if cx < 0.4:
        return "left"
    if cx > 0.6:
        return "right"
    return "middle"


def _scale_hint(value: float | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    number = float(match.group(1))
    if "cm" in str(value).lower():
        number /= 100
    if "ft" in str(value).lower() or "feet" in str(value).lower():
        number *= 0.3048
    return number if number > 0 else None


def program_from_reading(reading: dict, image_w: int, image_h: int, width_m: float | None) -> dict:
    aspect = reading.get("plot_aspect")
    try:
        aspect = float(aspect)
    except (TypeError, ValueError):
        aspect = image_w / max(1, image_h)
    aspect = min(max(aspect, 0.4), 3.0)

    width = _scale_hint(width_m) or _scale_hint(reading.get("plot_width_m"))
    if not width:
        width = 12.0
    width = min(max(width, 6.0), 30.0)
    depth = min(max(width / aspect, 6.0), 30.0)

    rooms = []
    for raw in reading.get("rooms") or []:
        if not isinstance(raw, dict):
            continue
        bbox = _norm_bbox(raw.get("bbox") or raw.get("box"), image_w, image_h)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        name = str(raw.get("name") or raw.get("label") or "Room").strip()
        room_type = normalise_type(raw.get("type"), name)
        area = max((x1 - x0) * (y1 - y0), 0.01)
        weight = min(max(area * 11.0, 0.8), 6.0)
        rooms.append(
            {
                "name": name,
                "type": room_type,
                "weight": round(weight, 2),
                "zone": _zone_for(x0, y0, x1, y1),
                "windows": int(raw.get("windows") or 0),
                "doors": int(raw.get("doors") or 1),
            }
        )
    if not rooms:
        raise VisionError("the vision model did not find any rooms in the image")

    rooms = rooms[:16]
    entrance = str(reading.get("entrance") or "").strip()
    if not entrance:
        for room in rooms:
            if room["type"] == "hall":
                entrance = room["name"]
                break
        else:
            entrance = rooms[0]["name"]

    return {
        "title": str(reading.get("title") or "Plan from image").strip(),
        "summary": str(reading.get("notes") or "").strip(),
        "plot": {"width_m": round(width, 2), "depth_m": round(depth, 2)},
        "rooms": rooms,
        "entrance": entrance,
        "notes": str(reading.get("notes") or "").strip(),
    }


def plan_from_image(
    data: bytes,
    filename: str = "",
    width_m: float | None = None,
    provider=None,
) -> dict:
    png, image_w, image_h = image_to_png(data, filename)
    provider = provider or get_provider()
    if provider is None or not provider.available():
        raise VisionError("no GenAI vision provider is reachable; start Ollama or set OPENAI_API_KEY")

    image_b64 = base64.b64encode(png).decode("ascii")
    hint = ""
    if width_m:
        hint = f"\nThe user says the plot is {width_m:.1f} m wide; use that scale."
    try:
        reading = provider.vision_json(
            VISION_PROMPT,
            f"Read this floor plan and return the JSON room program.{hint}",
            image_b64,
        )
    except GenAIError as exc:
        raise VisionError(f"vision model failed: {exc}") from exc

    program = program_from_reading(reading, image_w, image_h, width_m)
    program = normalise_program(program, "", 0)
    plan = program_to_layout(program, new_plan_id(program["title"]), 0)
    report = validate(plan)
    if not report["ok"]:
        report = validate(plan, repair=True)
    plan["validation"] = report
    plan["source"] = f"vlm:{provider.name}:{getattr(provider, 'vision_model', '')}"
    plan["image_size"] = [image_w, image_h]

    names = ", ".join(r.get("name", "Room") for r in plan["rooms"])
    message = (
        f"I read {len(plan['rooms'])} rooms from the plan ({names}) and rebuilt them as a "
        f"{program['plot']['width_m']:.1f} × {program['plot']['depth_m']:.1f} m layout. "
        + ("The geometry passed validation." if report["ok"] else "Some geometry warnings remain.")
    )
    return {
        "plan": plan,
        "message": message,
        "provider": f"vlm:{provider.name}",
        "warnings": [],
        "program": program,
        "reading": reading,
    }
