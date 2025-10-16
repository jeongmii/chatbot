from __future__ import annotations
from typing import Dict, Any
import json

# Default SYSTEM_TOOL_SOP for Eliva chatbot
DEFAULT_SYSTEM_TOOL_SOP = (
    "Follow the full Eliva persona and ELSIO DUNO policy from training. "
    "Answer only in Korean (5–250 words). "
    "You must first think by calling the select_strategy tool exactly once to perform analysis and choose a persuasion strategy, "
    "then produce a concise final answer for the user in Korean."
)


# Tool schema for function calling (OpenAI tools parameter)
SELECT_STRATEGY_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "select_strategy",
        "description": (
            "Perform analysis of the user's utterance and choose a persuasion strategy before answering. "
            "Provide your internal analysis, list a few candidate strategies, and state the chosen strategy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "The assistant's analysis of the user's intent and concerns.",
                    "minLength": 5,
                },
                "strategy_candidates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-5 candidate persuasion strategies considered.",
                    "minItems": 2,
                    "maxItems": 5,
                },
                "chosen_strategy": {
                    "type": "string",
                    "description": "The final chosen strategy to guide the response.",
                },
            },
            "required": ["analysis", "strategy_candidates", "chosen_strategy"],
            "additionalProperties": False,
        },
    },
}


def execute_select_strategy(arguments_json: str) -> str:
    """Executes the select_strategy tool server-side.

    For now we only validate payload shape and acknowledge.
    Returns a short string suitable as the tool result content.
    """
    try:
        payload = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return "INVALID_ARGUMENTS_JSON"

    if not isinstance(payload, dict):
        return "INVALID_ARGUMENTS_TYPE"

    analysis = payload.get("analysis")
    candidates = payload.get("strategy_candidates")
    chosen = payload.get("chosen_strategy")

    if not analysis or not isinstance(analysis, str):
        return "MISSING_ANALYSIS"
    if not candidates or not isinstance(candidates, list):
        return "MISSING_CANDIDATES"
    if not chosen or not isinstance(chosen, str):
        return "MISSING_CHOSEN"

    # Optionally, we could persist or audit this selection. For now return OK.
    return "OK"
