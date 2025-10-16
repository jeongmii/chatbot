import asyncio
import os
from typing import List, Dict, Any
from openai import OpenAI
from .config import get_settings

_settings = get_settings()


def _get_client() -> OpenAI:
    api_key = _settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured; set env or .env")
    return OpenAI(api_key=api_key)


def _create_completion_sync(messages: List[Dict[str, str]], model: str, temperature: float) -> Any:
    client = _get_client()
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )


async def create_chat_completion(messages: List[Dict[str, str]], model: str | None = None, temperature: float | None = None) -> Any:
    mdl = model or _settings.openai_model
    temp = 0.7 if temperature is None else temperature
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _create_completion_sync(messages, mdl, temp))
