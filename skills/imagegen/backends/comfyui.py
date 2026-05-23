"""ComfyUI image generation backend — workflow-based generation."""

import os, json, re, time, uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .base import BaseBackend


class ComfyUIBackend(BaseBackend):
    name = "comfyui"

    def __init__(self, config: dict):
        self.url = config.get("url", "http://127.0.0.1:8188").rstrip("/")
        self.workflow_json = config.get("workflow_json")
        self.default_params = {
            "model": config.get("model", ""),
            "sampler": config.get("sampler", "euler"),
            "scheduler": config.get("scheduler", "normal"),
            "vae": config.get("vae", ""),
            "width": config.get("width", 832),
            "height": config.get("height", 1216),
            "steps": config.get("steps", 28),
            "cfg": config.get("cfg", 7),
            "seed": config.get("seed", -1),
        }

    def _request(self, path: str, data: dict = None, method: str = "GET") -> dict:
        url = f"{self.url}{path}"
        body = json.dumps(data).encode("utf-8") if data else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = Request(url, data=body, headers=headers, method=method)
        try:
            resp = urlopen(req, timeout=300)
            return json.loads(resp.read())
        except HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"ComfyUI HTTP {e.code}: {msg}")
        except URLError as e:
            raise RuntimeError(f"ComfyUI connection error: {e.reason}")

    def _inject_params(self, workflow: dict, prompt: str, negative_prompt: str,
                       params: dict) -> dict:
        """Inject prompt/negative/seed/size into workflow nodes by class_type."""
        for node_id, node in workflow.items():
            ct = node.get("class_type", "")
            inputs = node.get("inputs", {})

            if ct == "KSampler" or ct == "KSamplerAdvanced":
                if "seed" in inputs:
                    seed = params.get("seed", -1)
                    inputs["seed"] = seed if seed >= 0 else int(time.time() * 1000) % (2**32)
                if "steps" in inputs:
                    inputs["steps"] = params.get("steps", inputs["steps"])
                if "cfg" in inputs:
                    inputs["cfg"] = params.get("cfg", inputs["cfg"])
                if "sampler_name" in inputs and params.get("sampler"):
                    inputs["sampler_name"] = params["sampler"]
                if "scheduler" in inputs and params.get("scheduler"):
                    inputs["scheduler"] = params["scheduler"]

            elif ct == "CLIPTextEncode":
                if "text" in inputs:
                    title = node.get("_meta", {}).get("title", "").lower()
                    if "negative" in title or "neg" in title:
                        inputs["text"] = negative_prompt
                    else:
                        inputs["text"] = prompt

            elif ct == "EmptyLatentImage":
                if "width" in inputs:
                    inputs["width"] = params.get("width", inputs["width"])
                if "height" in inputs:
                    inputs["height"] = params.get("height", inputs["height"])

            elif ct == "CheckpointLoaderSimple":
                if params.get("model") and "ckpt_name" in inputs:
                    inputs["ckpt_name"] = params["model"]

            elif ct == "VAELoader":
                if params.get("vae") and "vae_name" in inputs:
                    inputs["vae_name"] = params["vae"]

        return workflow

    def generate(self, prompt: str, negative_prompt: str, params: dict) -> Optional[Path]:
        merged = {**self.default_params, **params}

        if not self.workflow_json:
            raise RuntimeError("ComfyUI: no workflow configured")

        workflow = json.loads(json.dumps(self.workflow_json))
        workflow = self._inject_params(workflow, prompt, negative_prompt, merged)

        client_id = str(uuid.uuid4())
        payload = {"prompt": workflow, "client_id": client_id}
        result = self._request("/prompt", payload, "POST")
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI: no prompt_id in response")

        image_data = self._poll_result(prompt_id, timeout=300)
        if not image_data:
            raise RuntimeError("ComfyUI: generation timed out or failed")

        output_dir = params.get("output_dir",
                                str(Path(__file__).resolve().parents[2] / "styles" / "generated"))
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[\\/*?:"<>|\s]', '_', prompt[:50])[:40]
        fp = Path(output_dir) / f"comfy_{ts}_{safe}.png"
        fp.write_bytes(image_data)
        return fp

    def _poll_result(self, prompt_id: str, timeout: int = 300) -> Optional[bytes]:
        start = time.time()
        while time.time() - start < timeout:
            try:
                history = self._request(f"/history/{prompt_id}")
                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    for node_id, node_out in outputs.items():
                        images = node_out.get("images", [])
                        if images:
                            img_info = images[0]
                            filename = img_info["filename"]
                            subfolder = img_info.get("subfolder", "")
                            img_type = img_info.get("type", "output")
                            url = (f"{self.url}/view?filename={filename}"
                                   f"&subfolder={subfolder}&type={img_type}")
                            req = Request(url)
                            resp = urlopen(req, timeout=30)
                            return resp.read()
            except Exception:
                pass
            time.sleep(2)
        return None

    def test_connection(self) -> dict:
        try:
            system = self._request("/system_stats")
            obj_info = self._request("/object_info")
            models = []
            samplers = []
            schedulers = []
            if "CheckpointLoaderSimple" in obj_info:
                ckpt_input = obj_info["CheckpointLoaderSimple"].get("input", {}).get("required", {})
                if "ckpt_name" in ckpt_input:
                    models = ckpt_input["ckpt_name"][0] if isinstance(ckpt_input["ckpt_name"], list) else []
            if "KSampler" in obj_info:
                ks_input = obj_info["KSampler"].get("input", {}).get("required", {})
                if "sampler_name" in ks_input:
                    samplers = ks_input["sampler_name"][0] if isinstance(ks_input["sampler_name"], list) else []
                if "scheduler" in ks_input:
                    schedulers = ks_input["scheduler"][0] if isinstance(ks_input["scheduler"], list) else []
            return {
                "ok": True,
                "models": models if isinstance(models, list) else [],
                "samplers": samplers if isinstance(samplers, list) else [],
                "schedulers": schedulers if isinstance(schedulers, list) else [],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_default_params(self) -> dict:
        return dict(self.default_params)
