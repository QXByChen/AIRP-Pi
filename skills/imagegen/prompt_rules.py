"""Prompt replacement rules engine — text substitution and tag processing."""

import re
from typing import Optional


class PromptRules:
    def __init__(self, settings: dict):
        prompts_cfg = settings.get("prompts", {})
        self.quality_positive = prompts_cfg.get("quality_positive", "")
        self.quality_negative = prompts_cfg.get("quality_negative", "")
        self.fixed_positive = prompts_cfg.get("fixed_positive", "")
        self.fixed_positive_end = prompts_cfg.get("fixed_positive_end", "")
        self.fixed_negative = prompts_cfg.get("fixed_negative", "")
        self.replacement_rules: list[dict] = prompts_cfg.get("replacement_rules", [])

    def process(self, prompt: str, negative_prompt: str) -> tuple[str, str]:
        """Apply all prompt rules: quality tags, fixed prompts, replacements, dedup."""
        positive = self._build_positive(prompt)
        negative = self._build_negative(negative_prompt)

        positive = self._apply_replacements(positive)
        negative = self._apply_replacements(negative)

        positive = self._deduplicate_tags(positive)
        negative = self._deduplicate_tags(negative)

        return positive, negative

    def _build_positive(self, prompt: str) -> str:
        parts = []
        if self.quality_positive:
            parts.append(self.quality_positive)
        if self.fixed_positive:
            parts.append(self.fixed_positive)
        parts.append(prompt)
        if self.fixed_positive_end:
            parts.append(self.fixed_positive_end)
        return ", ".join(p for p in parts if p)

    def _build_negative(self, negative_prompt: str) -> str:
        parts = []
        if self.quality_negative:
            parts.append(self.quality_negative)
        if self.fixed_negative:
            parts.append(self.fixed_negative)
        if negative_prompt:
            parts.append(negative_prompt)
        return ", ".join(p for p in parts if p)

    def _apply_replacements(self, text: str) -> str:
        for rule in self.replacement_rules:
            if not rule.get("enabled", True):
                continue
            pattern = rule.get("find", "")
            replacement = rule.get("replace", "")
            if not pattern:
                continue
            if rule.get("regex"):
                try:
                    text = re.sub(pattern, replacement, text)
                except re.error:
                    pass
            else:
                text = text.replace(pattern, replacement)
        return text

    def _deduplicate_tags(self, text: str) -> str:
        tags = [t.strip() for t in text.split(",")]
        seen = set()
        result = []
        for tag in tags:
            if not tag:
                continue
            key = tag.lower().strip()
            if key not in seen:
                seen.add(key)
                result.append(tag)
        return ", ".join(result)
