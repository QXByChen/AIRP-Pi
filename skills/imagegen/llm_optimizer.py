"""LLM-based prompt optimization — converts scene descriptions to high-quality image tags."""

import json
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_SYSTEM_PROMPT = """你是一个专业的AI绘画提示词优化器。将用户提供的场景描述或简单标签转换为高质量的图像生成标签（英文Danbooru风格tag）。

规则：
1. 输出纯英文逗号分隔的标签，不要解释
2. 保留原始标签的核心含义，补充细节
3. 添加质量标签（如 masterpiece, best quality）
4. 添加适当的构图、光影、风格标签
5. 标签数量控制在10-20个
6. 不要输出任何非标签内容"""


class LLMPromptOptimizer:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.api_url = config.get("api_url", "").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 200)
        self.system_prompt = config.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

    def optimize(self, raw_tags: str, scene_context: str = "") -> str:
        if not self.enabled or not self.api_url:
            return raw_tags

        user_content = f"原始标签: {raw_tags}"
        if scene_context:
            user_content += f"\n场景上下文: {scene_context[:500]}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        url = f"{self.api_url}/v1/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = Request(url, data=body, headers=headers, method="POST")
        try:
            resp = urlopen(req, timeout=30)
            result = json.loads(resp.read())
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                optimized = content.strip()
                if optimized:
                    return optimized
        except (HTTPError, URLError, Exception) as e:
            print(f"[LLM Optimizer] Error: {e}")

        return raw_tags
