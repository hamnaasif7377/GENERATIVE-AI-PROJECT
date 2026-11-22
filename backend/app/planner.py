"""F1: natural-language requirements -> validated 2D layout."""

from __future__ import annotations

import math
import re

from .genai import GenAIError, get_provider
from .layout import ROOM_LABELS, new_plan_id
from .packing import normalise_program, program_to_layout
from .validator import validate

SYSTEM_PROMPT = """You are Plan2Walk's layout planner. Convert a user's housing requirements into a compact room program.
You do NOT draw walls or coordinates: deterministic geometry code does that from your program.

Return ONLY a JSON object with this shape:
{
  "title": "short project title",
  "summary": "one or two sentences describing the plan",
  "plot": {"width_m": 12.0, "depth_m": 10.0},
  "rooms": [
    {"name": "Living room", "type": "living_room", "weight": 3.2, "zone": "front", "windows": 2, "doors": 1}
  ],
  "entrance": "Hall",
  "notes": "optional"
}

Rules:
- type must be one of: living_room, kitchen, bedroom, bathroom, hall, other.
- weight is relative floor area, between 0.8 and 6.0.
- zone is one of: front, middle, back, left, right, center.
- windows is 0-3. Bedrooms, living rooms and kitchens need daylight.
- Keep the room counts the user asked for; never invent extra bedrooms.
- Include a hall when the user asks for one or when the plan has four or more rooms.
- width_m and depth_m are the plot size in metres, between 6 and 30.
- If the user asks for another option, keep the same requirements but change the zones or weights.
- Use clear human room names ("Bedroom 1", "Master bedroom", "Family bathroom").
"""


def _count(text: str, *patterns: str) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                pass
    return None


def _plot_size(text: str) -> tuple[float, float]:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?|ft|feet)?\s*(?:x|by|\*|×)\s*(\d+(?:\.\d+)?)",
        text,
    )
    if match:
        width, depth = float(match.group(1)), float(match.group(2))
        if "ft" in text or "feet" in text:
            width, depth = width * 0.3048, depth * 0.3048
        return min(max(width, 6.0), 30.0), min(max(depth, 6.0), 30.0)
    match = re.search(r"(\d{2,5})\s*(?:sq\.?\s*ft|square\s*feet|sqft)", text)
    if match:
        side = math.sqrt(float(match.group(1)) * 0.092903)
        return min(max(side, 6.0), 30.0), min(max(side * 0.85, 6.0), 30.0)
    match = re.search(r"(\d{2,4})\s*(?:m2|m²|square\s*metres?|sq\.?\s*m)", text)
    if match:
        side = math.sqrt(float(match.group(1)))
        return min(max(side, 6.0), 30.0), min(max(side * 0.85, 6.0), 30.0)
    return 12.0, 10.0


def offline_program(prompt: str) -> dict:
    """Deterministic fallback used when no GenAI provider is reachable."""
    text = prompt.lower()
    width, depth = _plot_size(text)

    bedrooms = _count(text, r"(\d+)\s*(?:bedrooms?|beds?|br)\b", r"bedrooms?\s*[:\-]?\s*(\d+)")
    bathrooms = _count(text, r"(\d+)\s*(?:bathrooms?|baths?|wc)\b", r"bathrooms?\s*[:\-]?\s*(\d+)")
    if bedrooms is None:
        bedrooms = 1 if "studio" in text else 2
    if bathrooms is None:
        bathrooms = 1
    bedrooms = min(max(bedrooms, 1), 8)
    bathrooms = min(max(bathrooms, 1), 4)

    rooms = [
        {"name": "Living room", "type": "living_room", "weight": 3.4, "zone": "front", "windows": 2, "doors": 1},
        {"name": "Kitchen", "type": "kitchen", "weight": 2.0, "zone": "front", "windows": 1, "doors": 1},
    ]
    if bedrooms >= 2 or "hall" in text or "entrance" in text:
        rooms.append({"name": "Hall", "type": "hall", "weight": 1.2, "zone": "middle", "windows": 0, "doors": 2})
    for i in range(bedrooms):
        rooms.append(
            {
                "name": "Master bedroom" if i == 0 and bedrooms > 1 else f"Bedroom {i + 1}",
                "type": "bedroom",
                "weight": 2.6 if i == 0 else 2.3,
                "zone": "back",
                "windows": 1,
                "doors": 1,
            }
        )
    for i in range(bathrooms):
        rooms.append(
            {
                "name": "Bathroom" if bathrooms == 1 else f"Bathroom {i + 1}",
                "type": "bathroom",
                "weight": 1.1,
                "zone": "middle",
                "windows": 1,
                "doors": 1,
            }
        )
    for keyword, name in (
        ("office", "Office"),
        ("study", "Study"),
        ("garage", "Garage"),
        ("store", "Store"),
        ("storage", "Store"),
        ("balcony", "Balcony"),
        ("terrace", "Terrace"),
    ):
        if keyword in text:
            rooms.append(
                {"name": name, "type": "other", "weight": 1.6, "zone": "middle", "windows": 1, "doors": 1}
            )

    return {
        "title": "Chat layout",
        "summary": f"A {width:.1f} × {depth:.1f} m plan with {bedrooms} bedroom(s) and {bathrooms} bathroom(s).",
        "plot": {"width_m": width, "depth_m": depth},
        "rooms": rooms,
        "entrance": "Hall" if any(r["type"] == "hall" for r in rooms) else "Living room",
        "notes": "Generated by the deterministic fallback because no GenAI provider was reachable.",
    }


def _template_message(plan: dict, program: dict) -> str:
    metrics = plan.get("validation", {}).get("metrics") or {}
    names = [r.get("name") or ROOM_LABELS.get(r.get("type"), "Room") for r in plan.get("rooms", [])]
    shown = ", ".join(names[:6]) + ("…" if len(names) > 6 else "")
    return (
        f"I built a {program['plot']['width_m']:.1f} × {program['plot']['depth_m']:.1f} m plan "
        f"with {len(names)} rooms ({shown}). "
        f"{metrics.get('doors', 0)} doors and {metrics.get('windows', 0)} windows, "
        f"{metrics.get('area_m2', 0):.0f} m² of floor area. "
        + ("The geometry passed validation." if plan.get("validation", {}).get("ok") else "Some geometry warnings remain.")
    )


def plan_from_prompt(prompt: str, provider=None, seed: int = 0) -> dict:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("describe the home you want first")
    provider = provider or get_provider()
    warnings: list[str] = []
    program = None
    used = "offline"

    if provider is not None and provider.available():
        variant_note = ""
        if seed:
            variant_note = (
                "\nThe user asked for another option: keep the same requirements but "
                "change the room zones and weights so the arrangement differs."
            )
        try:
            program = provider.chat_json(
                SYSTEM_PROMPT,
                f"Requirements:\n{prompt}{variant_note}",
                temperature=0.35 if not seed else 0.6,
                seed=seed,
            )
            used = provider.name
        except GenAIError as exc:
            warnings.append(f"GenAI provider failed ({exc}); used the deterministic fallback.")
    else:
        warnings.append("No GenAI provider is reachable; used the deterministic fallback.")

    if not program:
        program = offline_program(prompt)

    program = normalise_program(program, prompt, seed)
    plan = program_to_layout(program, new_plan_id(program["title"]), seed)
    report = validate(plan)
    if not report["ok"]:
        report = validate(plan, repair=True)
    plan["validation"] = report
    plan["source"] = used
    plan["prompt"] = prompt

    message = _template_message(plan, program)
    if warnings:
        message += "\n\n" + " ".join(warnings)
    return {
        "plan": plan,
        "message": message,
        "provider": used,
        "warnings": warnings,
        "program": program,
    }
