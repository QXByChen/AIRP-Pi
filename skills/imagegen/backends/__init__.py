"""Image generation backends."""

from .base import BaseBackend
from .novelai import NovelAIBackend
from .sd import SDWebUIBackend
from .comfyui import ComfyUIBackend
from .banana import BananaBackend

BACKENDS = {
    "novelai": NovelAIBackend,
    "sd": SDWebUIBackend,
    "comfyui": ComfyUIBackend,
    "banana": BananaBackend,
}
