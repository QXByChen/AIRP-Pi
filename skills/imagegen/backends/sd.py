"""Stable Diffusion WebUI (A1111/Forge) image generation backend."""

import os, json, base64, re
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .base import BaseBackend


class SDWebUIBackend(BaseBackend):
    name = "sd"

    def __init__(self, config: dict):
        self.url = config.get("url", "http://127.0.0.1:7860").rstrip("/")
        self.auth = config.get("auth", "")
        self.default_params = {
            "model": config.get("model", ""),
            "vae": config.get("vae", ""),
            "sampler": config.get("sampler", "Euler a"),
            "scheduler": config.get("scheduler", "Automatic"),
            "width": config.get("width", 832),
            "height": config.get("height", 1216),
            "steps": config.get("steps", 28),
            "cfg_scale": config.get("cfg_scale", 7),
            "clip_skip": config.get("clip_skip", 1),
            "seed": config.get("seed", -1),
            "hires_fix": config.get("hires_fix", False),
            "hires_upscaler": config.get("hires_upscaler", "Latent"),
            "hires_scale": config.get("hires_scale", 1.5),
            "hires_denoising": config.get("hires_denoising", 0.55),
            "hires_steps": config.get("hires_steps", 10),
            "restore_faces": config.get("restore_faces", False),
        }

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.auth:
            h["Authorization"] = f"Basic {base64.b64encode(self.auth.encode()).decode()}"
        return h

    def _request(self, path: str, data: dict = None, method: str = "GET") -> dict:
        url = f"{self.url}{path}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = Request(url, data=body, headers=self._headers(), method=method)
        try:
            resp = urlopen(req, timeout=300)
            return json.loads(resp.read())
        except HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"SD WebUI HTTP {e.code}: {msg}")
        except URLError as e:
            raise RuntimeError(f"SD WebUI connection error: {e.reason}")

    def generate(self, prompt: str, negative_prompt: str, params: dict) -> Optional[Path]:
        merged = {**self.default_params, **params}

        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": merged["width"],
            "height": merged["height"],
            "steps": merged["steps"],
            "cfg_scale": merged["cfg_scale"],
            "sampler_name": merged["sampler"],
            "scheduler": merged["scheduler"],
            "seed": merged["seed"],
            "clip_skip": merged["clip_skip"],
            "restore_faces": merged["restore_faces"],
            "n_iter": 1,
            "batch_size": 1,
        }

        if merged.get("hires_fix"):
            payload["enable_hr"] = True
            payload["hr_upscaler"] = merged["hires_upscaler"]
            payload["hr_scale"] = merged["hires_scale"]
            payload["denoising_strength"] = merged["hires_denoising"]
            payload["hr_second_pass_steps"] = merged["hires_steps"]

        if merged.get("model"):
            payload["override_settings"] = {"sd_model_checkpoint": merged["model"]}
            if merged.get("vae"):
                payload["override_settings"]["sd_vae"] = merged["vae"]

        result = self._request("/sdapi/v1/txt2img", payload, "POST")

        images = result.get("images", [])
        if not images:
            raise RuntimeError("SD WebUI: no images in response")

        image_data = base64.b64decode(images[0])
        output_dir = params.get("output_dir",
                                str(Path(__file__).resolve().parents[2] / "styles" / "generated"))
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[\\/*?:"<>|\s]', '_', prompt[:50])[:40]
        fp = Path(output_dir) / f"sd_{ts}_{safe}.png"
        fp.write_bytes(image_data)
        return fp

    def get_progress(self) -> dict:
        try:
            return self._request("/sdapi/v1/progress")
        except Exception:
            return {"progress": 0, "state": {"job": ""}}

    def test_connection(self) -> dict:
        try:
            models = self._request("/sdapi/v1/sd-models")
            samplers = self._request("/sdapi/v1/samplers")
            schedulers = self._request("/sdapi/v1/schedulers")
            vaes = self._request("/sdapi/v1/sd-vae")
            upscalers = self._request("/sdapi/v1/upscalers")
            return {
                "ok": True,
                "models": [m.get("title", m.get("model_name", "")) for m in models],
                "samplers": [s.get("name", "") for s in samplers],
                "schedulers": [s.get("name", s.get("label", "")) for s in schedulers],
                "vaes": [v.get("model_name", "") for v in vaes],
                "upscalers": [u.get("name", "") for u in upscalers],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_default_params(self) -> dict:
        return dict(self.default_params)
