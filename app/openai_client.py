import asyncio
import os
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .config import get_settings
from .tools import SELECT_STRATEGY_TOOL, execute_select_strategy

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


def _create_responses_sync(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    tools: Optional[list[dict]] = None,
    tool_choice: Optional[dict] = None,
) -> Any:
    client = _get_client()
    # Use chat.completions for compatibility, but pass tools (function call schema)
    # If your account has Responses API, switch to client.responses.create with input/messages accordingly.
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice
    return client.chat.completions.create(**kwargs)


async def create_responses_with_tools(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Any:
    mdl = model or _settings.openai_model
    temp = 0.7 if temperature is None else temperature
    loop = asyncio.get_running_loop()
    tools = [SELECT_STRATEGY_TOOL]
    # Let the model decide when to call; SOP will instruct to call once first
    return await loop.run_in_executor(
        None,
        lambda: _create_responses_sync(messages, mdl, temp, tools=tools),
    )


def _message_from_openai_assistant_toolcall(choice_message: Any) -> Dict[str, Any]:
    # Convert OpenAI assistant message with tool_calls into dict for reuse
    out: Dict[str, Any] = {"role": "assistant", "content": choice_message.content or ""}
    tool_calls = getattr(choice_message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]
    return out


def _build_tool_result_messages(tool_calls: list[dict]) -> list[dict]:
    tool_results: list[dict] = []
    for tc in tool_calls:
        func = tc.get("function", {})
        name = func.get("name")
        args = func.get("arguments", "{}")
        tool_call_id = tc.get("id")
        if name == "select_strategy":
            result = execute_select_strategy(args)
        else:
            result = "UNSUPPORTED_TOOL"
        tool_results.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        })
    return tool_results


def _aggregate_usage(u1: Optional[Any], u2: Optional[Any]) -> Dict[str, Optional[int]]:
    def val(x):
        return getattr(x, "prompt_tokens", None), getattr(x, "completion_tokens", None), getattr(x, "total_tokens", None)
    p1, c1, t1 = val(u1) if u1 else (None, None, None)
    p2, c2, t2 = val(u2) if u2 else (None, None, None)
    def add(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)
    return {
        "prompt_tokens": add(p1, p2),
        "completion_tokens": add(c1, c2),
        "total_tokens": add(t1, t2),
    }


async def run_structured_chain_with_tools(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Executes a two-stage tool-call chain:
    1) Model emits tool_calls (select_strategy)
    2) Server executes tools and feeds results back
    3) Model returns final assistant content

    Returns dict with: assistant_text, usage, tool_calls, tool_results
    """
    mdl = model or _settings.openai_model
    temp = 0.7 if temperature is None else temperature
    loop = asyncio.get_running_loop()

    # First call: allow tool calls
    first = await loop.run_in_executor(
        None,
        lambda: _create_responses_sync(messages, mdl, temp, tools=[SELECT_STRATEGY_TOOL]),
    )

    msg0 = first.choices[0].message
    tool_calls_raw = getattr(msg0, "tool_calls", None) or []
    assistant_message_with_tools = _message_from_openai_assistant_toolcall(msg0)
    usage_1 = getattr(first, "usage", None)

    if not tool_calls_raw:
        # No tool call; return content directly
        return {
            "assistant_text": msg0.content or "",
            "usage": {
                "prompt_tokens": getattr(usage_1, "prompt_tokens", None) if usage_1 else None,
                "completion_tokens": getattr(usage_1, "completion_tokens", None) if usage_1 else None,
                "total_tokens": getattr(usage_1, "total_tokens", None) if usage_1 else None,
            },
            "tool_calls": [],
            "tool_results": [],
        }

    tool_calls = [
        {
            "id": tc.id,
            "type": tc.type,
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        }
        for tc in tool_calls_raw
    ]
    tool_result_messages = _build_tool_result_messages(tool_calls)

    # Second call: include assistant tool call message + tool results
    messages2: List[Dict[str, Any]] = messages + [assistant_message_with_tools] + tool_result_messages
    second = await loop.run_in_executor(
        None,
        lambda: _create_responses_sync(messages2, mdl, temp),
    )
    msg1 = second.choices[0].message
    usage_2 = getattr(second, "usage", None)

    usage = _aggregate_usage(usage_1, usage_2)
    return {
        "assistant_text": msg1.content or "",
        "usage": usage,
        "tool_calls": tool_calls,
        "tool_results": tool_result_messages,
        "assistant_tool_message": assistant_message_with_tools,
    }
