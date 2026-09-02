"""T3.6-T3.9: production adapters — LiteLLM arbiter + post/exec/completions transports.

Adapters are thin: every external call goes through an injectable callable so
tests use fakes (#31). The LiteLLM arbiter call is made once per check with
config knobs (#2): temperature 0, max_tokens 512, timeout 30s, no LiteLLM
retries. Provider is selected by the LiteLLM model id; api_key is passed only
when Config.arbiter_api_key is set (otherwise LiteLLM uses OPENROUTER_API_KEY /
OPENAI_API_KEY / ANTHROPIC_API_KEY from the environment).
"""

from __future__ import annotations

import errno
import json
import logging
import secrets
import subprocess  # noqa: S404 — exec transport is a deliberate design decision
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
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

_log = logging.getLogger("admz.dispatch")

# Injectable seams ----------------------------------------------------------

Poster = Callable[[str, dict[str, str], bytes, int], tuple[int, str]]
"""endpoint, headers, body, timeout -> (status, text)."""

Runner = Callable[[str, str, int], tuple[int, str, str]]
"""command, timeout -> (exit_code, stdout, stderr)."""

Completer = Callable[..., str]
"""model, system, user, timeout, max_tokens, temperature[, api_key] -> reply text."""


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
    api_key: str = "",
) -> str:
    import litellm

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "num_retries": 0,
    }
    if api_key:
        kwargs["api_key"] = api_key
    response = litellm.completion(**kwargs)
    return str(response.choices[0].message.content or "")


# --- Connectivity probes (admin console) --------------------------------------

PING_SYSTEM = (
    "You are a connectivity probe for Agent DMZ. "
    "Reply with the probe token exactly as given and nothing else."
)
_PING_MAX_TOKENS = 64


@dataclass(frozen=True)
class ConnectionTestResult:
    """Outcome of an admin connectivity probe. Failures keep traceback/detail."""

    ok: bool
    summary: str
    reply: str = ""
    detail: str = ""
    traceback: str = ""
    model: str = ""
    endpoint: str = ""


def new_probe_token() -> str:
    return "admz-ok-" + secrets.token_hex(8)


def ping_user_message(token: str) -> str:
    return f"Repeat this token exactly, with no extra words: {token}"


def format_exception_report(exc: BaseException) -> tuple[str, str]:
    """Human-readable exception chain plus a full traceback (no secrets added)."""
    chain: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        name = f"{type(cur).__module__}.{type(cur).__qualname__}"
        extras: list[str] = []
        if isinstance(cur, OSError):
            if cur.errno is not None:
                extras.append(f"errno={cur.errno}")
                code = errno.errorcode.get(cur.errno)
                if code:
                    extras.append(code)
            winerror = getattr(cur, "winerror", None)
            if winerror:
                extras.append(f"winerror={winerror}")
        suffix = f" ({', '.join(extras)})" if extras else ""
        message = str(cur).strip() or "(no message)"
        chain.append(f"{name}{suffix}: {message}")
        nxt = cur.__cause__
        if nxt is None and not cur.__suppress_context__:
            nxt = cur.__context__
        cur = nxt
    summary = "\n".join(chain) if chain else type(exc).__name__
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return summary, tb


def ping_arbiter(
    config: Config,
    completer: Completer = _litellm_completer,
    *,
    token: str | None = None,
) -> ConnectionTestResult:
    """LiteLLM round-trip: ask the configured arbiter model to echo a token."""
    probe = token or new_probe_token()
    model = config.arbiter_model
    try:
        reply = completer(
            model,
            PING_SYSTEM,
            ping_user_message(probe),
            config.arbiter_timeout,
            min(_PING_MAX_TOKENS, config.arbiter_max_tokens),
            0.0,
            config.arbiter_api_key,
        )
    except Exception as exc:  # noqa: BLE001 — surface the real provider error
        summary, tb = format_exception_report(exc)
        return ConnectionTestResult(
            ok=False,
            summary=summary,
            traceback=tb,
            model=model,
        )
    text = reply if isinstance(reply, str) else str(reply)
    if probe not in text:
        return ConnectionTestResult(
            ok=False,
            summary=(
                "Arbiter responded, but the probe token was not in the reply. "
                "The model is reachable; the echo check failed."
            ),
            reply=text,
            model=model,
        )
    return ConnectionTestResult(
        ok=True,
        summary="Arbiter connection succeeded; the model echoed the probe token.",
        reply=text,
        model=model,
    )


def ping_provider(
    delivery: dict[str, Any],
    *,
    default_timeout: int,
    poster: Poster = _default_poster,
    runner: Runner = _default_runner,
    token: str | None = None,
) -> ConnectionTestResult:
    """Probe saved delivery settings. Completions: chat echo; post/exec: reachability."""
    protocol = (delivery.get("protocol") or "post").strip()
    timeout = int(delivery.get("timeout") or default_timeout)
    probe = token or new_probe_token()
    if protocol == "completions":
        return _ping_completions(delivery, timeout=timeout, poster=poster, probe=probe)
    if protocol == "exec":
        return _ping_exec(delivery, timeout=timeout, runner=runner, probe=probe)
    if protocol == "post":
        return _ping_post(delivery, timeout=timeout, poster=poster, probe=probe)
    return ConnectionTestResult(
        ok=False,
        summary=f"Unknown delivery protocol {protocol!r}.",
    )


def _ping_completions(
    delivery: dict[str, Any],
    *,
    timeout: int,
    poster: Poster,
    probe: str,
) -> ConnectionTestResult:
    endpoint = (delivery.get("endpoint") or "").strip()
    model = (delivery.get("model") or "").strip()
    if not endpoint:
        return ConnectionTestResult(
            ok=False,
            summary="Saved delivery has no endpoint URL. Save an OpenAI-compatible "
            "/chat/completions URL first.",
            model=model,
        )
    if not model:
        return ConnectionTestResult(
            ok=False,
            summary="Saved delivery has no model name.",
            endpoint=endpoint,
        )
    headers = {"Content-Type": "application/json"}
    headers.update(delivery.get("headers") or {})
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": PING_SYSTEM},
                {"role": "user", "content": ping_user_message(probe)},
            ],
            "temperature": 0,
            "max_tokens": _PING_MAX_TOKENS,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        status, text = poster(endpoint, headers, body, timeout)
    except Exception as exc:  # noqa: BLE001
        summary, tb = format_exception_report(exc)
        return ConnectionTestResult(
            ok=False,
            summary=summary,
            traceback=tb,
            model=model,
            endpoint=endpoint,
        )
    if status != 200:
        return ConnectionTestResult(
            ok=False,
            summary=f"Provider HTTP {status} from {endpoint}.",
            detail=text,
            model=model,
            endpoint=endpoint,
        )
    try:
        data = json.loads(text)
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return ConnectionTestResult(
            ok=False,
            summary="Provider returned HTTP 200 but not a parseable chat-completions body.",
            detail=text,
            model=model,
            endpoint=endpoint,
        )
    if not isinstance(content, str):
        return ConnectionTestResult(
            ok=False,
            summary="Provider completions content is not a string.",
            detail=text,
            model=model,
            endpoint=endpoint,
        )
    if probe not in content:
        return ConnectionTestResult(
            ok=False,
            summary=(
                "Provider responded, but the probe token was not in the reply. "
                "The endpoint is reachable; the echo check failed."
            ),
            reply=content,
            detail=text,
            model=model,
            endpoint=endpoint,
        )
    return ConnectionTestResult(
        ok=True,
        summary="Provider connection succeeded; the model echoed the probe token.",
        reply=content,
        model=model,
        endpoint=endpoint,
    )


def _ping_post(
    delivery: dict[str, Any],
    *,
    timeout: int,
    poster: Poster,
    probe: str,
) -> ConnectionTestResult:
    endpoint = (delivery.get("endpoint") or "").strip()
    if not endpoint:
        return ConnectionTestResult(
            ok=False,
            summary="Saved delivery has no endpoint URL.",
        )
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    headers.update(delivery.get("headers") or {})
    body = ping_user_message(probe).encode("utf-8")
    try:
        status, text = poster(endpoint, headers, body, timeout)
    except Exception as exc:  # noqa: BLE001
        summary, tb = format_exception_report(exc)
        return ConnectionTestResult(
            ok=False,
            summary=summary,
            traceback=tb,
            endpoint=endpoint,
        )
    if status != 200:
        return ConnectionTestResult(
            ok=False,
            summary=f"Provider HTTP {status} from {endpoint}.",
            detail=text,
            endpoint=endpoint,
        )
    return ConnectionTestResult(
        ok=True,
        summary="Provider HTTP POST succeeded (HTTP 200).",
        reply=text,
        endpoint=endpoint,
    )


def _ping_exec(
    delivery: dict[str, Any],
    *,
    timeout: int,
    runner: Runner,
    probe: str,
) -> ConnectionTestResult:
    command = (delivery.get("command") or "").strip()
    if not command:
        return ConnectionTestResult(
            ok=False,
            summary="Saved delivery has no command.",
        )
    try:
        exit_code, stdout, stderr = runner(command, ping_user_message(probe), timeout)
    except Exception as exc:  # noqa: BLE001
        summary, tb = format_exception_report(exc)
        return ConnectionTestResult(ok=False, summary=summary, traceback=tb)
    if exit_code == -1 and stderr == "timeout":
        return ConnectionTestResult(
            ok=False,
            summary=f"Provider command timed out after {timeout}s.",
            detail=stderr,
        )
    if exit_code != 0:
        return ConnectionTestResult(
            ok=False,
            summary=f"Provider command exited {exit_code}.",
            reply=stdout,
            detail=stderr,
        )
    return ConnectionTestResult(
        ok=True,
        summary="Provider command exited 0.",
        reply=stdout,
        detail=stderr,
    )


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
    """Arbiter over LiteLLM; one call per check, fail-closed verdicts."""

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
        _log.info("arbiter check side=%s action=%s model=%s", side, action_id, self._config.arbiter_model)
        try:
            reply = self._completer(
                self._config.arbiter_model,
                "\n\n".join(parts),
                "Inspect the payload and answer with the verdict JSON.",
                self._config.arbiter_timeout,
                self._config.arbiter_max_tokens,
                self._config.arbiter_temperature,
                self._config.arbiter_api_key,
            )
        except Exception as exc:  # noqa: BLE001 — classify by LiteLLM exception class
            name = type(exc).__name__
            detail = str(exc).strip()
            summary = f"{name}: {detail}" if detail else name
            _log.exception("arbiter LiteLLM call failed (%s)", summary)
            if any(token in name.lower() for token in ("auth", "key", "badrequest", "notfound")):
                raise ArbiterConfigFault(f"arbiter configuration fault: {summary}") from exc
            raise ArbiterTransportError(f"arbiter transport failure: {summary}") from exc
        return parse_verdict(reply)

    def ping(self, *, token: str | None = None) -> ConnectionTestResult:
        """Admin connectivity probe; does not use the security-arbiter prompts."""
        return ping_arbiter(self._config, self._completer, token=token)


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
