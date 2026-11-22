"""GenAI access layer.

Primary provider: a local Ollama server (OpenAI-style chat + vision, JSON mode).
Optional provider: any OpenAI-compatible endpoint when ``OPENAI_API_KEY`` is set.
The rest of the app only sees ``chat_json`` / ``vision_json`` and a health dict.
"""

from __future__ import annotations

import ast
import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_TEXT_MODEL = "qwen2.5:3b"
DEFAULT_VISION_MODEL = "qwen2.5vl:3b"
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_OPENAI_TEXT = "gpt-4o-mini"
DEFAULT_OPENAI_VISION = "gpt-4o-mini"


class GenAIError(RuntimeError):
    pass


def _post(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise GenAIError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GenAIError(f"cannot reach {url}: {exc}") from exc


def _get(url: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        raise GenAIError(str(exc)) from exc


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    if isinstance(text, dict):
        return text
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    if start < 0:
        raise GenAIError(f"model did not return JSON: {text[:200]}")
    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise GenAIError(f"unterminated JSON object: {text[:200]}")
    candidate = text[start:end]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                value = ast.literal_eval(cleaned)
                if isinstance(value, dict):
                    return value
            except (ValueError, SyntaxError):
                pass
    raise GenAIError(f"could not parse JSON: {candidate[:300]}")


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str | None = None, text_model: str | None = None, vision_model: str | None = None):
        self.host = (host or os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA).rstrip("/")
        self.text_model = text_model or os.getenv("PLAN2WALK_TEXT_MODEL") or DEFAULT_TEXT_MODEL
        self.vision_model = vision_model or os.getenv("PLAN2WALK_VISION_MODEL") or DEFAULT_VISION_MODEL

    def available(self) -> bool:
        try:
            _get(f"{self.host}/api/tags", timeout=1.5)
            return True
        except GenAIError:
            return False

    def models(self) -> list[str]:
        try:
            data = _get(f"{self.host}/api/tags", timeout=2.0)
            return [m.get("name", "") for m in data.get("models", [])]
        except GenAIError:
            return []

    def _chat(self, messages: list[dict], model: str, temperature: float, seed: int | None, max_tokens: int) -> dict:
        options = {"temperature": temperature, "num_predict": max_tokens}
        if seed is not None:
            options["seed"] = seed
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": options,
        }
        data = _post(f"{self.host}/api/chat", payload, timeout=240)
        content = (data.get("message") or {}).get("content") or ""
        return extract_json(content)

    def chat_json(self, system: str, user: str, temperature: float = 0.3, seed: int | None = None, max_tokens: int = 1400) -> dict:
        return self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            self.text_model,
            temperature,
            seed,
            max_tokens,
        )

    def vision_json(self, system: str, user: str, image_b64: str, temperature: float = 0.15, max_tokens: int = 1400) -> dict:
        return self._chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user, "images": [image_b64]},
            ],
            self.vision_model,
            temperature,
            None,
            max_tokens,
        )

    def health(self) -> dict:
        return {
            "provider": self.name,
            "host": self.host,
            "text_model": self.text_model,
            "vision_model": self.vision_model,
            "available": self.available(),
            "models": self.models(),
        }


class OpenAIProvider:
    name = "openai"

    def __init__(self):
        self.host = (os.getenv("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE).rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.text_model = os.getenv("PLAN2WALK_TEXT_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_TEXT
        self.vision_model = os.getenv("PLAN2WALK_VISION_MODEL") or os.getenv("OPENAI_VISION_MODEL") or DEFAULT_OPENAI_VISION

    def available(self) -> bool:
        return bool(self.api_key)

    def models(self) -> list[str]:
        return [self.text_model, self.vision_model]

    def _chat(self, messages: list[dict], model: str, temperature: float, seed: int | None, max_tokens: int) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if seed is not None:
            payload["seed"] = seed
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            raise GenAIError(f"OpenAI HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GenAIError(f"cannot reach OpenAI: {exc}") from exc
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return extract_json(content)

    def chat_json(self, system: str, user: str, temperature: float = 0.3, seed: int | None = None, max_tokens: int = 1400) -> dict:
        return self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            self.text_model,
            temperature,
            seed,
            max_tokens,
        )

    def vision_json(self, system: str, user: str, image_b64: str, temperature: float = 0.15, max_tokens: int = 1400) -> dict:
        return self._chat(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                },
            ],
            self.vision_model,
            temperature,
            None,
            max_tokens,
        )

    def health(self) -> dict:
        return {
            "provider": self.name,
            "host": self.host,
            "text_model": self.text_model,
            "vision_model": self.vision_model,
            "available": self.available(),
            "models": self.models(),
        }


def get_provider():
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return OllamaProvider()
