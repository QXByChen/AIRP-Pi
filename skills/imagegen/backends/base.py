"""Abstract base class for image generation backends."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseBackend(ABC):
    name: str = ""

    @abstractmethod
    def generate(self, prompt: str, negative_prompt: str, params: dict) -> Optional[Path]:
        """Generate image synchronously. Returns path to saved file or None on failure."""
        ...

    @abstractmethod
    def test_connection(self) -> dict:
        """Test connection to the backend service.
        Returns dict with 'ok' bool and available options (models, samplers, etc.)."""
        ...

    def get_default_params(self) -> dict:
        """Return default generation parameters for this backend."""
        return {}
