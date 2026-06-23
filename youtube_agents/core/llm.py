"""Small LLM clients used by optional creative stages."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from youtube_agents.core.env import load_dotenv


class OpenAIChatClient:
    """Minimal standard-library client for OpenAI-compatible chat completions."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 60,
    ):
        load_dotenv()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_IDEA_MODEL") or "gpt-4o-mini"
        self.base_url = (base_url or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        return bool(self.api_key)

    def json_chat(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "error": "OPENAI_API_KEY is not configured."}

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return {"ok": True, "data": json.loads(content), "model": self.model}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"HTTP {error.code}: {body}", "model": self.model}
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as error:
            return {"ok": False, "error": str(error), "model": self.model}


class OllamaChatClient:
    """Minimal standard-library client for Ollama's local chat API."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 120,
    ):
        load_dotenv()
        self.model = model or os.getenv("OLLAMA_IDEA_MODEL") or "llama3.1"
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        return True

    def json_chat(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.8},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["message"]["content"]
            return {"ok": True, "data": json.loads(content), "model": self.model}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"HTTP {error.code}: {body}", "model": self.model}
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
            return {"ok": False, "error": str(error), "model": self.model}
