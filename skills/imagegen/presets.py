"""Character presets and outfit management for image generation."""

import json
from pathlib import Path
from typing import Optional


class PresetsManager:
    def __init__(self, settings: dict):
        self.characters: list[dict] = settings.get("characters", [])

    def find_character(self, name: str) -> Optional[dict]:
        for char in self.characters:
            if char.get("name", "") == name or char.get("name_en", "") == name:
                return char
            triggers = char.get("triggers", [])
            if name in triggers:
                return char
        return None

    def apply_preset(self, prompt: str, negative_prompt: str,
                     char_name: str = "", outfit: str = "") -> tuple[str, str]:
        """Apply character preset to prompt. Returns (positive, negative)."""
        char = self.find_character(char_name) if char_name else None
        if not char:
            return prompt, negative_prompt

        char_positive = char.get("positive", "")
        char_negative = char.get("negative", "")

        if outfit and char.get("outfits"):
            for o in char["outfits"]:
                if o.get("name") == outfit or o.get("name_en") == outfit:
                    char_positive = o.get("positive", char_positive)
                    break

        if char_positive:
            prompt = f"{char_positive}, {prompt}"
        if char_negative:
            negative_prompt = f"{negative_prompt}, {char_negative}" if negative_prompt else char_negative

        return prompt, negative_prompt

    def list_characters(self) -> list[dict]:
        return [{"id": i, "name": c.get("name", ""), "name_en": c.get("name_en", ""),
                 "outfits": [o.get("name", "") for o in c.get("outfits", [])]}
                for i, c in enumerate(self.characters)]

    def add_character(self, char_data: dict) -> int:
        self.characters.append(char_data)
        return len(self.characters) - 1

    def update_character(self, index: int, char_data: dict):
        if 0 <= index < len(self.characters):
            self.characters[index] = char_data

    def remove_character(self, index: int):
        if 0 <= index < len(self.characters):
            self.characters.pop(index)

    def to_dict(self) -> list[dict]:
        return self.characters
