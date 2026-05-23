"""NovelAI image generation backend — supports V3/V4/V4.5 full series."""

import os, sys, json, io, re, zipfile, base64, time
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .base import BaseBackend

API_URL = "https://image.novelai.net/ai/generate-image"

V4_MODELS = {
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-curated-preview",
    "nai-diffusion-4-full",
}
V3_MODELS = {
    "nai-diffusion-3",
    "nai-diffusion-furry-3",
}

DEFAULT_NEGATIVE = (
    "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, "
    "bad anatomy, bad hands, worst quality, bad quality, jpeg artifacts, "
    "very displeasing, chromatic aberration, halftone, multiple views, logo, "
    "too many watermarks, mismatched pupils, glowing eyes, negative space, "
    "blank page, low quality, sketch, censor"
)


def _build_v4_params(prompt: str, negative_prompt: str, params: dict,
                     char_prompts: list = None) -> dict:
    return {
        "params_version": 3,
        "width": params.get("width", 832),
        "height": params.get("height", 1216),
        "scale": params.get("scale", 5),
        "sampler": params.get("sampler", "k_euler_ancestral"),
        "steps": params.get("steps", 28),
        "n_samples": 1,
        "ucPreset": 2,
        "qualityToggle": True,
        "autoSmea": params.get("smea", False),
        "dynamic_thresholding": False,
        "controlnet_strength": 1,
        "legacy": False,
        "add_original_image": True,
        "cfg_rescale": params.get("cfg_rescale", 0),
        "noise_schedule": params.get("schedule", "karras"),
        "legacy_v3_extend": False,
        "skip_cfg_above_sigma": None,
        "use_coords": True,
        "normalize_reference_strength_multiple": True,
        "inpaintImg2ImgStrength": 1,
        "v4_prompt": {
            "caption": {
                "base_caption": prompt,
                "char_captions": char_prompts or [],
            },
            "use_coords": True,
            "use_order": True,
        },
        "v4_negative_prompt": {
            "caption": {
                "base_caption": negative_prompt,
                "char_captions": [],
            },
            "legacy_uc": False,
        },
        "legacy_uc": False,
        "seed": params.get("seed", 0),
        "characterPrompts": char_prompts or [],
        "negative_prompt": negative_prompt,
        "deliberate_euler_ancestral_bug": False,
        "prefer_brownian": True,
        "image_format": "png",
    }


def _build_v3_params(prompt: str, negative_prompt: str, params: dict) -> dict:
    return {
        "width": params.get("width", 832),
        "height": params.get("height", 1216),
        "scale": params.get("scale", 5),
        "sampler": params.get("sampler", "k_euler_ancestral"),
        "steps": params.get("steps", 28),
        "n_samples": 1,
        "ucPreset": params.get("ucPreset", 0),
        "qualityToggle": True,
        "sm": params.get("smea", False),
        "sm_dyn": params.get("smea_dyn", False),
        "dynamic_thresholding": False,
        "controlnet_strength": 1,
        "legacy": False,
        "add_original_image": False,
        "cfg_rescale": params.get("cfg_rescale", 0),
        "noise_schedule": "native",
        "seed": params.get("seed", 0),
        "negative_prompt": negative_prompt,
    }


class NovelAIBackend(BaseBackend):
    name = "novelai"

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.site = config.get("site", "official")
        self.other_site_url = config.get("other_site_url", "")
        self.model = config.get("model", "nai-diffusion-4-5-curated")
        self.default_params = {
            "sampler": config.get("sampler", "k_euler_ancestral"),
            "schedule": config.get("schedule", "karras"),
            "scale": config.get("scale", 5),
            "cfg_rescale": config.get("cfg_rescale", 0),
            "smea": config.get("smea", False),
            "smea_dyn": config.get("smea_dyn", False),
            "width": config.get("width", 832),
            "height": config.get("height", 1216),
            "steps": config.get("steps", 28),
            "seed": config.get("seed", 0),
        }

    def _get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        key = os.environ.get("NOVELAI_API_KEY", "")
        if key:
            return key
        for env_path in [Path(__file__).resolve().parents[3] / ".env", Path.cwd() / ".env"]:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("NOVELAI_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        return ""

    def _get_api_url(self) -> str:
        if self.site == "other" and self.other_site_url:
            return self.other_site_url.rstrip("/") + "/ai/generate-image"
        return API_URL

    def generate(self, prompt: str, negative_prompt: str, params: dict) -> Optional[Path]:
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("NovelAI API key not configured")

        merged = {**self.default_params, **params}
        model = params.get("model", self.model)

        if model in V4_MODELS:
            parameters = _build_v4_params(prompt, negative_prompt, merged,
                                          params.get("char_prompts"))
        else:
            parameters = _build_v3_params(prompt, negative_prompt, merged)

        body = json.dumps({
            "input": prompt,
            "model": model,
            "parameters": parameters,
        }).encode("utf-8")

        req = Request(
            self._get_api_url(), data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Origin": "https://novelai.net",
                "Referer": "https://novelai.net/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            method="POST",
        )

        try:
            resp = urlopen(req, timeout=120)
        except HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"NovelAI HTTP {e.code}: {msg}")
        except URLError as e:
            raise RuntimeError(f"NovelAI network error: {e.reason}")

        raw = resp.read()
        image_data = self._extract_image(raw)
        if not image_data:
            raise RuntimeError("NovelAI: failed to extract image from response")

        output_dir = params.get("output_dir", str(Path(__file__).resolve().parents[2] / "styles" / "generated"))
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[\\/*?:"<>|\s]', '_', prompt[:50])[:40]
        fp = Path(output_dir) / f"nai_{ts}_{safe}.png"
        fp.write_bytes(image_data)
        return fp

    def _extract_image(self, raw: bytes) -> Optional[bytes]:
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            for name in zf.namelist():
                if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    return zf.read(name)
        except (zipfile.BadZipFile, Exception):
            pass
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    b = base64.b64decode(line[5:].strip())
                    if len(b) > 100:
                        return b
                except Exception:
                    continue
        if len(raw) > 100:
            return raw
        return None

    def test_connection(self) -> dict:
        api_key = self._get_api_key()
        if not api_key:
            return {"ok": False, "error": "API key not configured"}
        try:
            req = Request(
                "https://api.novelai.net/user/subscription",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return {"ok": True, "subscription": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_default_params(self) -> dict:
        return {**self.default_params, "model": self.model}
