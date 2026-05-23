"""Banana backend — OpenAI-format multimodal image generation (Grok, Gemini, etc.)."""

import os, json, re, base64, time
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .base import BaseBackend

ASPECT_RATIOS = {
    "1:1": (1024, 1024),
    "9:16": (832, 1216),
    "16:9": (1216, 832),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
}


class BananaBackend(BaseBackend):
    name = "banana"

    def __init__(self, config: dict):
        self.api_url = config.get("api_url", "").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.aspect_ratio = config.get("aspect_ratio", "9:16")
        self.use_grok_format = config.get("use_grok_format", False)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def generate(self, prompt: str, negative_prompt: str, params: dict) -> Optional[Path]:
        if not self.api_url:
            raise RuntimeError("Banana: API URL not configured")

        model = params.get("model", self.model)
        aspect = params.get("aspect_ratio", self.aspect_ratio)
        use_grok = params.get("use_grok_format", self.use_grok_format)

        if use_grok:
            image_data = self._generate_grok(prompt, model, aspect)
        else:
            image_data = self._generate_openai_format(prompt, negative_prompt, model, aspect)

        if not image_data:
            raise RuntimeError("Banana: no image data in response")

        output_dir = params.get("output_dir",
                                str(Path(__file__).resolve().parents[2] / "styles" / "generated"))
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[\\/*?:"<>|\s]', '_', prompt[:50])[:40]
        fp = Path(output_dir) / f"banana_{ts}_{safe}.png"
        fp.write_bytes(image_data)
        return fp

    def _generate_grok(self, prompt: str, model: str, aspect: str) -> Optional[bytes]:
        """Grok native image generation format: /v1/images/generations"""
        url = f"{self.api_url}/v1/images/generations"
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if aspect in ASPECT_RATIOS:
            w, h = ASPECT_RATIOS[aspect]
            payload["size"] = f"{w}x{h}"

        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, headers=self._headers(), method="POST")
        try:
            resp = urlopen(req, timeout=120)
            result = json.loads(resp.read())
            data_list = result.get("data", [])
            if data_list:
                b64 = data_list[0].get("b64_json", "")
                if b64:
                    return base64.b64decode(b64)
                img_url = data_list[0].get("url", "")
                if img_url:
                    return urlopen(Request(img_url), timeout=30).read()
        except HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Grok HTTP {e.code}: {msg}")
        except URLError as e:
            raise RuntimeError(f"Grok connection error: {e.reason}")
        return None

    def _generate_openai_format(self, prompt: str, negative_prompt: str,
                                model: str, aspect: str) -> Optional[bytes]:
        """OpenAI chat completions format with image output (Gemini, etc.)."""
        url = f"{self.api_url}/v1/chat/completions"

        full_prompt = prompt
        if negative_prompt:
            full_prompt += f"\n\nAvoid: {negative_prompt}"

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"Generate an image: {full_prompt}"}
            ],
            "max_tokens": 1,
        }

        if "gemini" in model.lower():
            payload["generation_config"] = {
                "response_modalities": ["IMAGE", "TEXT"],
            }
            if aspect in ASPECT_RATIOS:
                w, h = ASPECT_RATIOS[aspect]
                payload["generation_config"]["image_size"] = {"width": w, "height": h}

        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, headers=self._headers(), method="POST")

        try:
            resp = urlopen(req, timeout=180)
            result = json.loads(resp.read())
            return self._extract_image_from_response(result)
        except HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Banana HTTP {e.code}: {msg}")
        except URLError as e:
            raise RuntimeError(f"Banana connection error: {e.reason}")

    def _extract_image_from_response(self, result: dict) -> Optional[bytes]:
        """Extract image from various response formats."""
        choices = result.get("choices", [])
        if not choices:
            return None

        message = choices[0].get("message", {})
        content = message.get("content", "")

        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image" or "image" in part:
                        img_data = part.get("image", part.get("data", ""))
                        if isinstance(img_data, dict):
                            b64 = img_data.get("data", img_data.get("b64_json", ""))
                        else:
                            b64 = img_data
                        if b64:
                            return base64.b64decode(b64)
                    if part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            b64 = url.split(",", 1)[1] if "," in url else ""
                            if b64:
                                return base64.b64decode(b64)
                        elif url:
                            return urlopen(Request(url), timeout=30).read()

        if isinstance(content, str):
            import re as _re
            b64_match = _re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', content)
            if b64_match:
                return base64.b64decode(b64_match.group(1))

        return None

    def test_connection(self) -> dict:
        if not self.api_url:
            return {"ok": False, "error": "API URL not configured"}
        try:
            url = f"{self.api_url}/v1/models"
            req = Request(url, headers=self._headers())
            resp = urlopen(req, timeout=10)
            result = json.loads(resp.read())
            models = [m.get("id", "") for m in result.get("data", [])]
            return {"ok": True, "models": models}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_default_params(self) -> dict:
        return {
            "model": self.model,
            "aspect_ratio": self.aspect_ratio,
            "use_grok_format": self.use_grok_format,
        }
