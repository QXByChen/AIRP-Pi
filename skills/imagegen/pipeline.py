"""Image generation pipeline — orchestrates the full generation flow."""

import json, os, re, threading
from pathlib import Path
from typing import Optional

from .task_store import TaskStore
from .gallery import Gallery
from .presets import PresetsManager
from .prompt_rules import PromptRules
from .llm_optimizer import LLMPromptOptimizer
from .backends import BACKENDS
from .backends.base import BaseBackend

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "styles" / "imagegen_settings.json"
GENERATED_DIR = Path(__file__).resolve().parent.parent / "styles" / "generated"

DEFAULT_SETTINGS = {
    "enabled": True,
    "auto_trigger": True,
    "active_backend": "novelai",
    "llm_optimize": {
        "enabled": False,
        "api_url": "",
        "api_key": "",
        "model": "",
        "temperature": 0.7,
        "max_tokens": 200,
        "system_prompt": "",
    },
    "backends": {
        "sd": {
            "url": "http://127.0.0.1:7860", "auth": "", "model": "", "vae": "",
            "sampler": "Euler a", "scheduler": "Automatic",
            "width": 832, "height": 1216, "steps": 28, "cfg_scale": 7,
            "clip_skip": 1, "seed": -1,
            "hires_fix": False, "hires_upscaler": "Latent",
            "hires_scale": 1.5, "hires_denoising": 0.55, "hires_steps": 10,
            "restore_faces": False,
        },
        "novelai": {
            "api_key": "", "site": "official", "other_site_url": "",
            "model": "nai-diffusion-4-5-curated",
            "sampler": "k_euler_ancestral", "schedule": "karras",
            "scale": 5, "cfg_rescale": 0,
            "smea": False, "smea_dyn": False,
            "width": 832, "height": 1216, "steps": 28, "seed": 0,
        },
        "comfyui": {
            "url": "http://127.0.0.1:8188", "workflow_json": None,
            "model": "", "sampler": "", "scheduler": "", "vae": "",
            "width": 832, "height": 1216, "steps": 28, "cfg": 7, "seed": -1,
        },
        "banana": {
            "api_url": "", "api_key": "", "model": "",
            "aspect_ratio": "9:16", "use_grok_format": False,
        },
    },
    "prompts": {
        "quality_positive": "best quality, amazing quality, very aesthetic, absurdres",
        "quality_negative": "lowres, bad anatomy, bad hands, worst quality, low quality",
        "fixed_positive": "", "fixed_positive_end": "", "fixed_negative": "",
        "replacement_rules": [],
    },
    "fab": {
        "enabled": True,
        "video_mode": False,
        "desktop_pet": False,
        "bg_color": "#5b8a5b",
        "icon_color": "#ffffff",
        "opacity": 1.0,
        "size": 50,
        "position": {"top": "65vh", "left": "20px"},
    },
    "characters": [],
    "imagegen_worldbook": {
        "enabled": True,
        "books_dir": "imagegen_worldbooks",
        "bindings": {
            "_default": [],
        },
    },
}


class ImagePipeline:
    def __init__(self, settings_path: Path = SETTINGS_PATH):
        self.settings_path = settings_path
        self.settings = self._load_settings()
        self.task_store = TaskStore()
        self.gallery = Gallery(GENERATED_DIR)
        self._backends_cache: dict[str, BaseBackend] = {}

    def _load_settings(self) -> dict:
        if self.settings_path.exists():
            try:
                loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                return self._deep_merge(DEFAULT_SETTINGS, loaded)
            except (json.JSONDecodeError, Exception):
                pass
        return dict(DEFAULT_SETTINGS)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def save_settings(self, updates: dict = None):
        if updates:
            self.settings = self._deep_merge(self.settings, updates)
        os.makedirs(self.settings_path.parent, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        self._backends_cache.clear()

    def reload_settings(self):
        self.settings = self._load_settings()
        self._backends_cache.clear()

    def is_enabled(self) -> bool:
        return self.settings.get("enabled", False)

    def is_auto_trigger(self) -> bool:
        return self.settings.get("auto_trigger", False)

    def get_backend(self, name: str = None) -> BaseBackend:
        name = name or self.settings.get("active_backend", "novelai")
        if name not in self._backends_cache:
            backend_cls = BACKENDS.get(name)
            if not backend_cls:
                raise ValueError(f"Unknown backend: {name}")
            config = self.settings.get("backends", {}).get(name, {})
            self._backends_cache[name] = backend_cls(config)
        return self._backends_cache[name]

    def submit(self, raw_tags: str, turn_index: int = -1,
               char_name: str = "", context: str = "",
               backend_name: str = None, extra_params: dict = None) -> str:
        """Submit a generation task. Returns task_id. Runs generation in background thread."""
        backend_name = backend_name or self.settings.get("active_backend", "novelai")
        task_id = self.task_store.create_task(raw_tags, backend_name, turn_index)

        def _run():
            try:
                self.task_store.update_status(task_id, "generating", 0.1)
                result_path = self._execute(raw_tags, char_name, context,
                                            backend_name, extra_params)
                if result_path:
                    rel_path = str(result_path)
                    self.task_store.update_status(task_id, "done", 1.0, image_path=rel_path)
                    self.gallery.add(
                        image_path=rel_path, prompt=raw_tags,
                        negative_prompt="", backend=backend_name,
                        turn_index=turn_index, task_id=task_id,
                    )
                else:
                    self.task_store.update_status(task_id, "error", error="No image generated")
            except Exception as e:
                self.task_store.update_status(task_id, "error", error=str(e))

        threading.Thread(target=_run, daemon=True).start()
        return task_id

    def _execute(self, raw_tags: str, char_name: str = "", context: str = "",
                 backend_name: str = None, extra_params: dict = None) -> Optional[Path]:
        """Execute the full pipeline synchronously. Returns image path."""
        prompt = raw_tags
        negative_prompt = ""

        presets = PresetsManager(self.settings)
        prompt, negative_prompt = presets.apply_preset(prompt, negative_prompt, char_name)

        rules = PromptRules(self.settings)
        prompt, negative_prompt = rules.process(prompt, negative_prompt)

        llm_cfg = self.settings.get("llm_optimize", {})
        optimizer = LLMPromptOptimizer(llm_cfg)
        if optimizer.enabled:
            prompt = optimizer.optimize(prompt, context)

        backend = self.get_backend(backend_name)
        params = {"output_dir": str(GENERATED_DIR)}
        if extra_params:
            params.update(extra_params)

        return backend.generate(prompt, negative_prompt, params)

    def get_settings(self) -> dict:
        return dict(self.settings)

    def test_backend_connection(self, backend_name: str) -> dict:
        try:
            backend = self.get_backend(backend_name)
            return backend.test_connection()
        except Exception as e:
            return {"ok": False, "error": str(e)}
