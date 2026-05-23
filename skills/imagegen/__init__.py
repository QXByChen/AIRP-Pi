"""AIRP-Pi Image Generation System — multi-backend image generation with auto-trigger."""

from .pipeline import ImagePipeline
from .task_store import TaskStore

_instance: "ImagePipeline | None" = None


def get_pipeline() -> ImagePipeline:
    global _instance
    if _instance is None:
        _instance = ImagePipeline()
    return _instance


def reset_pipeline():
    global _instance
    _instance = None
