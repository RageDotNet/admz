"""T3.6-T3.9: production adapters — LiteLLM arbiter + post/exec/completions transports.

Adapters are thin: every external call goes through an injectable callable so
tests use fakes (#31). The LiteLLM arbiter call is made once per check with
config knobs (#2): temperature 0, max_tokens 512, timeout 30s, no LiteLLM
retries.
"""

from __future__ import annotations

import json
import subprocess  # noqa: S404 — exec transport is a deliberate design decision
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from admz.core.config import Config
from admz.dispatch.arbiter_prompts import resolve_prompts
from admz.dispatch.interfaces import (
    ArbiterConfigFault,
    ArbiterTransportError,
    Framing,
    ProviderResult,
    Verdict,
)
from admz.dispatch.verdict import parse_verdict

# Injectable seams ----------------------------------------------------------

Poster = Callable[[str, dict[str, str], bytes, int], tuple[int, str]]
"""endpoint, headers, body, timeout -> (status, text)."""

Runner = Callable[[str, str, int], tuple[int, str, str]]
"""command, timeout -> (exit_code, stdout, stderr)."""

Completer = Callable[[str, str, str, int, int, float], str]
"""model, system, user, timeout, max_tokens, temperature -> reply text."""


def _default_poster(
    endpoint: str, headers: dict[str, str], body: bytes, timeout: int
) -> tuple[int, str]:
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _default_runner(command: str, stdin_text: str, timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            shell=True,  # noqa: S602 — configured command line by design
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=stdin_text,  # framing on stdin (dispatch-v2.md exec)
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"


def _litellm_completer(
    model: str,
    system: str,
    user: str,
    timeout: int,
    max_tokens: int,
    temperature: float,
) -> str:
    import litellm

    response = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        num_retries=0,
    )
    return str(response.choices[0].message.content or "")


# --- Framing builders (dispatch-v2.md "Input framing") ------------------------


def build_unstructured_framing(
    *,
    instructions: str,
    response_schema: dict[str, Any],
    request_payload: dict[str, Any],
    previous_error: str | None = None,
) -> str:
    blocks = [instructions]
    if previous_error:
        blocks.append(
            "ERRORS FROM YOUR PREVIOUS INVOCATION (correct your output):\n" + previous_error
        )
    blocks.append(
        "The schema your response JSON must conform to:\n"
        + json.dumps(response_schema, ensure_ascii=False, indent=2)
    )
    blocks.append("REQUEST JSON FOLLOWS:\n" + json.dumps(request_payload, ensure_ascii=False))
    return "\n\n".join(blocks)


def build_structured_framing(
    *,
    instructions: str,
    response_schema: dict[str, Any],
    request_payload: dict[str, Any],
    previous_error: str | None = None,
) -> tuple[str, str]:
    system = instructions
    if previous_error:
        system += (
            "\n\nERRORS FROM YOUR PREVIOUS INVOCATION (correct your output):\n" + previous_error
        )
    system += (
        "\n\nThe schema your response JSON must conform to:\n"
        + json.dumps(response_schema, ensure_ascii=False, indent=2)
        + "\nRespond with ONLY the response JSON, nothing else."
    )
    user = json.dumps(request_payload, ensure_ascii=False)
    return system, user


# --- T3.6: LiteLLM arbiter adapter -------------------------------------------


class LiteLLMArbiterClient:
    """Arbiter over LiteLLM/OpenRouter; one call per check, fail-closed verdicts."""

    def __init__(self, config: Config, completer: Completer = _litellm_completer):
        self._config = config
        self._completer = completer

    def check(
        self,
        *,
        side: str,
        action_id: str,
        payload: Any,
        extra_instructions: str = "",
    ) -> Verdict:
        req_prompt, resp_prompt = resolve_prompts()
        base = req_prompt if side == "request" else resp_prompt
        parts = [base]
        if extra_instructions:
            parts.append(
                "Additional instructions for this action (provider-supplied, reviewed):\n"
                + extra_instructions
            )
        parts.append(f"Action: {action_id}")
        parts.append(f"{side} payload to inspect:\n{json.dumps(payload, ensure_ascii=False)}")
        parts.append('Reply with ONLY valid JSON: {"approved": ..., "reason": ...}')
        try:
            reply = self._completer(
                self._config.arbiter_model,
                "\n\n".join(parts),
                "Inspect the payload and answer with the verdict JSON.",
                self._config.arbiter_timeout,
                self._config.arbiter_max_tokens,
                self._config.arbiter_temperature,
            )
        except Exception as exc:  # noqa: BLE001 — classify by LiteLLM exception class
            name = type(exc).__name__
            if any(token in name.lower() for token in ("auth", "key", "badrequest", "notfound")):
                raise ArbiterConfigFault(f"arbiter configuration fault: {name}") from exc
            raise ArbiterTransportError(f"arbiter transport failure: {name}") from exc
        return parse_verdict(reply)


# --- T3.7-T3.9: provider transports ------------------------------------------


class PostTransport:
    """T3.7: HTTP POST with verbatim configured headers."""

    def __init__(self, poster: Poster = _default_poster):
        self._poster = poster

    def deliver(self, framing: Framing) -> ProviderResult:
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        headers.update(framing.headers or {})
        try:
            status, text = self._poster(
                framing.endpoint, headers, framing.text.encode("utf-8"), framing.timeout
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(error_class="transport", error_detail=str(exc))
        if status != 200:
            return ProviderResult(error_class="protocol", error_detail=f"HTTP {status}: {text}")
        return _parse_payload(text)


class ExecTransport:
    """T3.8: local subprocess; framing on stdin, JSON payload on stdout."""

    def __init__(self, runner: Runner = _default_runner):
        self._runner = runner

    def deliver(self, framing: Framing) -> ProviderResult:
        try:
            exit_code, stdout, stderr = self._runner(framing.command, framing.text, framing.timeout)
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(error_class="transport", error_detail=str(exc))
        if exit_code == -1 and stderr == "timeout":
            return ProviderResult(
                error_class="timeout", error_detail="timed out", exit_code=exit_code, stderr=stderr
            )
        if exit_code != 0:
            return ProviderResult(
                error_class="protocol",
                error_detail=f"exit code {exit_code}: {stderr}",
                exit_code=exit_code,
                stderr=stderr,
            )
        result = _parse_payload(stdout)
        result.exit_code = exit_code
        result.stderr = stderr
        return result


class CompletionsTransport:
    """T3.9: OpenAI-compatible POST to the configured chat-completions URL."""

    def __init__(self, poster: Poster = _default_poster):
        self._poster = poster

    def deliver(self, framing: Framing) -> ProviderResult:
        headers = {"Content-Type": "application/json"}
        headers.update(framing.headers or {})
        body = json.dumps(
            {
                "model": framing.model,
                "messages": [
                    {"role": "system", "content": framing.system_prompt},
                    {"role": "user", "content": framing.user_prompt},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            status, text = self._poster(
                framing.endpoint, headers, body, framing.timeout
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(error_class="transport", error_detail=str(exc))
        if status != 200:
            return ProviderResult(error_class="protocol", error_detail=f"HTTP {status}: {text}")
        try:
            data = json.loads(text)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
            return ProviderResult(
                error_class="protocol", error_detail="unparseable completions response"
            )
        if not isinstance(content, str):
            return ProviderResult(
                error_class="protocol", error_detail="completions content is not a string"
            )
        return _parse_payload(content)


def _parse_payload(text: str) -> ProviderResult:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return ProviderResult(error_class="protocol", error_detail="unparseable JSON response")
    if not isinstance(payload, dict):
        return ProviderResult(error_class="protocol", error_detail="response is not an object")
    return ProviderResult(payload=payload)
