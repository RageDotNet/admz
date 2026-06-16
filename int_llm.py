"""Internal (trusted) LLM agent with CRM access via LiteLLM + OpenRouter."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv
from litellm import completion

from crmtool import CRM_TOOLS, run_tool
from llm_logging import get_logger, log_json

load_dotenv()

logger = get_logger("int_llm")

MODEL = "openrouter/openai/gpt-oss-120b:free"

SYSTEM_PROMPT = """You are the internal trusted agent for a company CRM system.
You have access to private customer records through CRM tools.
Use the tools to look up contacts, search records, and add notes when asked.
Answer clearly and only share CRM data that is relevant to the user's request."""


def _require_api_key() -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")
    return api_key


def _message_to_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, dict):
        return message
    return dict(message)


def _usage_dict(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump(exclude_none=True)
    if isinstance(usage, dict):
        return usage
    return dict(usage)


def _execute_tool_call(tool_call: Any) -> str:
    name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as exc:
        logger.warning(
            "Tool call parse error tool=%s id=%s error=%s",
            name,
            tool_call.id,
            exc,
        )
        return json.dumps({"error": f"Invalid tool arguments: {exc}"})

    log_json(logger, logging.INFO, f"Tool call tool={name} id={tool_call.id} args=", arguments)

    try:
        result = run_tool(name, arguments)
        content = json.dumps(result, default=str)
        log_json(logger, logging.INFO, f"Tool result tool={name} id={tool_call.id} result=", result)
        return content
    except Exception as exc:  # noqa: BLE001 - return tool errors to the model
        logger.exception("Tool call failed tool=%s id=%s", name, tool_call.id)
        return json.dumps({"error": str(exc)})


def chat(user_message: str, history: list[dict[str, Any]] | None = None) -> str:
    """Send a message and run the tool-calling loop until the model replies."""
    api_key = _require_api_key()
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    logger.info("Chat started user_message=%s", user_message)

    turn = 0
    while True:
        turn += 1
        logger.info(
            "Inference request turn=%d model=%s message_count=%d tool_count=%d",
            turn,
            MODEL,
            len(messages),
            len(CRM_TOOLS),
        )
        log_json(logger, logging.DEBUG, "Inference request messages=", messages)

        response = completion(
            model=MODEL,
            messages=messages,
            tools=CRM_TOOLS,
            api_key=api_key,
        )
        assistant_message = response.choices[0].message
        assistant_dict = _message_to_dict(assistant_message)
        usage = _usage_dict(response)

        log_json(
            logger,
            logging.INFO,
            f"Inference response turn={turn} finish_reason={response.choices[0].finish_reason} usage={usage} message=",
            assistant_dict,
        )

        messages.append(assistant_dict)

        tool_calls = getattr(assistant_message, "tool_calls", None)
        if not tool_calls:
            content = assistant_message.content or ""
            logger.info("Chat completed turn=%d final_response=%s", turn, content.strip())
            return content.strip()

        logger.info("Inference requested %d tool call(s) turn=%d", len(tool_calls), turn)

        for tool_call in tool_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": _execute_tool_call(tool_call),
                }
            )


def main() -> None:
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(chat(prompt))
        return

    print("Internal LLM (CRM). Type 'quit' to exit.")
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        print(f"\nAgent: {chat(user_input)}")


if __name__ == "__main__":
    main()
