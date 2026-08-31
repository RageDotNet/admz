"""Trusted internal CRM provider for Agent DMZ v2.

Modes:

- ``python crm_provider.py register`` — publish the CRM actions
  (``crm_search``, ``crm_add_note``) as schema packages to the DMZ's
  agent-facing REST API (``POST /v2/actions``), using the JSON Schema files
  in ``schemas/`` next to this script (``examples/schemas/``).

- ``python crm_provider.py update`` — submit a NEW VERSION of each action
  (``PUT /v2/actions/{id}``); the active version keeps serving until an
  admin approves the new one.

- ``python crm_provider.py enroll [pattern]`` — as a client, request
  enrollment in every directory action whose id contains ``pattern``
  (default ``crm``).

- ``python crm_provider.py client <action_id> [request JSON]`` — invoke an
  action as a client via ``POST /v2/actions/{id}/invoke``; the request
  payload comes from the argument, or stdin if omitted. Sample files:
  ``requests/crm_search_request.json``, ``requests/crm_add_note_request.json``.

- ``python crm_provider.py run`` — implement the **exec delivery protocol**
  (dispatch-v2.md): read the unstructured framing on stdin, extract the
  request JSON after the ``REQUEST JSON FOLLOWS:`` marker, fulfill it, and
  write the response payload as JSON to stdout. Failures go to stderr with a
  non-zero exit code so the DMZ records them as failed attempts.

- ``python crm_provider.py serve [host] [port]`` — OpenAI-compatible
  ``POST /v1/chat/completions`` listener for the **completions** delivery
  protocol. Prints the endpoint URL on start. Host/port default to
  ``127.0.0.1:8090`` (or ``CRM_SERVE_HOST`` / ``CRM_SERVE_PORT``).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

# Allow `python examples/crm_provider.py` from the repo root.
_EXAMPLES_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EXAMPLES_DIR.parent
sys.path.insert(0, str(_EXAMPLES_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from crmtool import add_contact_note, search_contacts

# Bearer keys from the admin console (reveal-once). Put them in the repo-root
# `.env` as DMZ_PROVIDER_KEY / DMZ_CLIENT_KEY so a reissued key is not a code change.
PROVIDER_KEY = os.getenv("DMZ_PROVIDER_KEY", "")
CLIENT_KEY = os.getenv("DMZ_CLIENT_KEY") or PROVIDER_KEY
DMZ_BASE_URL = os.getenv("DMZ_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# Always the directory beside this file — not cwd — so register/update work
# from the repo root or from examples/.
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

REQUEST_MARKER = "REQUEST JSON FOLLOWS:"


# --- fulfillment handlers ------------------------------------------------------

def fulfill_crm_search(payload: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []

    def add_matches(query: str) -> None:
        for contact in search_contacts(query):
            if contact["id"] not in seen:
                seen.add(contact["id"])
                records.append(contact)

    if name := payload.get("name"):
        add_matches(str(name))
    if company := payload.get("company"):
        add_matches(str(company))

    return {"records": records}


def fulfill_crm_add_note(payload: dict[str, Any]) -> dict[str, Any]:
    contact_id = str(payload["contact_id"])
    note = str(payload["note"])
    record = add_contact_note(contact_id, note)
    return {"record": record}


HANDLERS = {
    "crm_search": fulfill_crm_search,
    "crm_add_note": fulfill_crm_add_note,
}


# --- register mode ---------------------------------------------------------------


def _load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _action_package(
    action_id: str,
    description: str,
    provider_instructions: str,
    *,
    request_risk: str = "",
    response_risk: str = "",
) -> dict[str, Any]:
    package = {
        "id": action_id,
        "description": description,
        "request_schema": _load_schema(f"{action_id}_request"),
        "response_schema": _load_schema(f"{action_id}_response"),
        "provider_instructions": provider_instructions,
    }
    # Risk focus for each arbiter side: the request side of these actions
    # mainly risks prompt injection (untrusted client text in name/note
    # fields), the response side mainly risks exfiltration (contact data).
    if request_risk:
        package["request_risk"] = request_risk
    if response_risk:
        package["response_risk"] = response_risk
    return package


ACTION_PACKAGES = [
    _action_package(
        "crm_search",
        "Query CRM contacts by customer name and/or company name. Returns the "
        "matching contact records, or an empty list if none matched.",
        "The request JSON contains optional 'name' and/or 'company' fields. "
        "Return {\"records\": [...]} with every matching contact; return an "
        "empty list when nothing matches. Output ONLY the response JSON.",
        request_risk="injection",
        response_risk="exfiltration",
    ),
    _action_package(
        "crm_add_note",
        "Append a note to an existing CRM contact record. Returns the updated "
        "contact record.",
        "The request JSON contains 'contact_id' and 'note'. Append the note "
        "to that contact and return {\"record\": {...}} of the updated "
        "contact. Output ONLY the response JSON.",
        request_risk="injection",
        response_risk="exfiltration",
    ),
]


def _require_keys(*, client: bool = False) -> int | None:
    """Return an exit code if the needed bearer key is missing."""
    needed = CLIENT_KEY if client else PROVIDER_KEY
    var = "DMZ_CLIENT_KEY or DMZ_PROVIDER_KEY" if client else "DMZ_PROVIDER_KEY"
    if needed:
        return None
    print(
        f"Set {var} in {_REPO_ROOT / '.env'} (or the environment).",
        file=sys.stderr,
    )
    return 2


def register() -> int:
    """POST each schema package to /v2/actions with the provider key."""
    if (rc := _require_keys()) is not None:
        return rc
    failures = 0
    for package in ACTION_PACKAGES:
        req = urllib.request.Request(
            f"{DMZ_BASE_URL}/v2/actions",
            data=json.dumps(package).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {PROVIDER_KEY}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                body = json.loads(resp.read().decode("utf-8"))
                print(f"[register] {package['id']}: {resp.status} {json.dumps(body)}")
        except urllib.error.HTTPError as exc:
            failures += 1
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"[register] {package['id']}: HTTP {exc.code} {detail}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[register] {package['id']}: {exc}", file=sys.stderr)

    if failures:
        print(f"[register] {failures} action(s) failed to register", file=sys.stderr)
        return 1
    print("[register] all actions submitted; awaiting admin approval (state 'pending')")
    return 0


# --- shared v2 API helper --------------------------------------------------------


def _api(
    method: str,
    path: str,
    body: dict[str, Any] | list[dict[str, Any]] | None = None,
    *,
    key: str | None = None,
) -> tuple[int, Any, str]:
    """Call the DMZ v2 REST API; returns (status, parsed_json_or_None, raw_text)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{DMZ_BASE_URL}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key or PROVIDER_KEY}",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, _maybe_json(text), text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, _maybe_json(text), text


def _maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _report(label: str, status: int, body: Any, ok: tuple[int, ...] = (200, 201)) -> bool:
    if status in ok:
        print(f"[{label}] {status} {json.dumps(body)}")
        return True
    print(f"[{label}] HTTP {status} {json.dumps(body)}", file=sys.stderr)
    return False


# --- update mode -----------------------------------------------------------------


def update() -> int:
    """PUT each schema package to /v2/actions/{id}: submits a NEW pending version."""
    if (rc := _require_keys()) is not None:
        return rc
    failures = 0
    for package in ACTION_PACKAGES:
        status, body, _ = _api("PUT", f"/v2/actions/{package['id']}", package)
        if not _report("update", status, body, ok=(200, 201)):
            failures += 1
    if failures:
        print(f"[update] {failures} action(s) failed to update", file=sys.stderr)
        return 1
    print("[update] new versions submitted; awaiting admin approval")
    return 0


# --- enroll mode -----------------------------------------------------------------


def enroll(pattern: str = "crm") -> int:
    """As a client, request enrollment in every directory action matching `pattern`."""
    if (rc := _require_keys(client=True)) is not None:
        return rc
    status, body, _ = _api("GET", "/v2/actions", key=CLIENT_KEY)
    items = body.get("items") if isinstance(body, dict) else None
    if status != 200 or not isinstance(items, list):
        print(f"[enroll] could not list actions: HTTP {status} {body}", file=sys.stderr)
        return 1
    targets = [
        entry.get("id")
        for entry in items
        if isinstance(entry, dict) and pattern in str(entry.get("id", ""))
    ]
    if not targets:
        print(f"[enroll] no directory actions match {pattern!r}")
        return 0
    failures = 0
    for action_id in targets:
        status, body, _ = _api("POST", f"/v2/actions/{action_id}/enroll", {}, key=CLIENT_KEY)
        if status == 409:  # already enrolled/requested — fine
            print(f"[enroll] {action_id}: 409 already enrolled/requested")
            continue
        if not _report("enroll", status, body, ok=(200, 201)):
            failures += 1
    return 1 if failures else 0


# --- client mode (invoke) ----------------------------------------------------------


def client_invoke(action_id: str, payload_json: str | None) -> int:
    """Invoke an action as a client: `client <action> [request JSON]`.

    The request payload is the argument if given, else read from stdin.
    """
    if (rc := _require_keys(client=True)) is not None:
        return rc
    raw = payload_json if payload_json is not None else sys.stdin.read()
    # Convenience: if the argument names an existing file, read the JSON from it.
    if payload_json is not None:
        candidate = Path(payload_json)
        if candidate.is_file():
            raw = candidate.read_text(encoding="utf-8")
    print(f"[client] POST {DMZ_BASE_URL}/v2/actions/{action_id}/invoke", file=sys.stderr)
    print(f"[client] key: {CLIENT_KEY[:16]}... ({len(CLIENT_KEY)} chars)", file=sys.stderr)
    print(f"[client] request payload (from {'argv' if payload_json is not None else 'stdin'}):", file=sys.stderr)
    print(raw, file=sys.stderr)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[client] request payload is not valid JSON: {exc}", file=sys.stderr)
        return 1
    status, body, text = _api(
        "POST", f"/v2/actions/{action_id}/invoke", payload, key=CLIENT_KEY
    )
    print(f"[client] HTTP status: {status}", file=sys.stderr)
    print(f"[client] raw response: {text[:2000]}", file=sys.stderr)
    if status == 200:
        print(json.dumps(body, indent=2))
        return 0
    print(f"[client] HTTP {status} {json.dumps(body)}", file=sys.stderr)
    return 1


# --- run mode (exec delivery protocol) -------------------------------------------
# The framing carries no action id (one delivery config serves all of this
# provider's actions), so the action is inferred from the request payload shape.


def _extract_request_payload(framing: str) -> dict[str, Any]:
    if REQUEST_MARKER not in framing:
        raise ValueError(f"framing is missing the {REQUEST_MARKER!r} marker")
    payload = json.loads(framing.split(REQUEST_MARKER, 1)[1].strip())
    if not isinstance(payload, dict):
        raise ValueError("request payload is not a JSON object")
    return payload


def _infer_action_id(payload: dict[str, Any]) -> str:
    if "contact_id" in payload and "note" in payload:
        return "crm_add_note"
    if "name" in payload or "company" in payload:
        return "crm_search"
    raise ValueError(
        f"cannot infer action from request payload (keys: {sorted(payload)}); "
        "expected crm_search (name/company) or crm_add_note (contact_id/note)"
    )


def _utf8_stdio() -> None:
    """Windows consoles default to cp1252; emoji in framing/JSON needs UTF-8."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _fulfill(payload: dict[str, Any]) -> dict[str, Any]:
    action_id = _infer_action_id(payload)
    return HANDLERS[action_id](payload)


def run() -> int:
    _utf8_stdio()
    framing = sys.stdin.read()
    try:
        payload = _extract_request_payload(framing)
        response_payload = _fulfill(payload)
    except Exception as exc:  # noqa: BLE001 — any failure is a failed attempt
        print(f"crm_provider: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(response_payload, ensure_ascii=False))
    return 0


# --- serve mode (OpenAI-compatible chat completions) -----------------------------


DEFAULT_SERVE_HOST = os.getenv("CRM_SERVE_HOST", "127.0.0.1")
DEFAULT_SERVE_PORT = int(os.getenv("CRM_SERVE_PORT", "8090"))


def _request_payload_from_messages(messages: list[Any]) -> dict[str, Any]:
    """The DMZ user turn is the request JSON; use the last parseable user object."""
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, str):
            continue
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("no user message contained a JSON object request payload")


def _openai_completion(content: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def create_serve_app():
    """Flask app exposing POST /v1/chat/completions (and /chat/completions)."""
    from flask import Flask, jsonify, request

    app = Flask("crm_provider_serve")
    app.json.ensure_ascii = False

    def chat_completions():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": {"message": "JSON object body required", "type": "invalid_request_error"}}), 400
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return jsonify({"error": {"message": "messages array required", "type": "invalid_request_error"}}), 400
        model = str(body.get("model") or "crm-provider")
        try:
            payload = _request_payload_from_messages(messages)
            response_payload = _fulfill(payload)
        except Exception as exc:  # noqa: BLE001 — surface as a failed completions attempt
            return jsonify({"error": {"message": str(exc), "type": "server_error"}}), 500
        content = json.dumps(response_payload, ensure_ascii=False)
        return jsonify(_openai_completion(content, model))

    app.add_url_rule(
        "/v1/chat/completions",
        view_func=chat_completions,
        methods=["POST"],
        endpoint="v1_chat_completions",
    )
    app.add_url_rule(
        "/chat/completions",
        view_func=chat_completions,
        methods=["POST"],
        endpoint="chat_completions",
    )
    return app


def serve(host: str = DEFAULT_SERVE_HOST, port: int = DEFAULT_SERVE_PORT) -> int:
    app = create_serve_app()
    endpoint = f"http://{host}:{port}/v1/chat/completions"
    print(f"[serve] OpenAI-compatible chat completions: {endpoint}", flush=True)
    print(
        "[serve] Set the provider delivery method to completions with this endpoint "
        "(any model name is accepted).",
        flush=True,
    )
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    return 0


def main() -> None:
    _utf8_stdio()
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "register":
        sys.exit(register())
    if mode == "update":
        sys.exit(update())
    if mode == "enroll":
        sys.exit(enroll(sys.argv[2] if len(sys.argv) > 2 else "crm"))
    if mode == "run":
        sys.exit(run())
    if mode == "client":
        if len(sys.argv) < 3:
            print("usage: crm_provider.py client <action_id> [request JSON]", file=sys.stderr)
            sys.exit(2)
        sys.exit(client_invoke(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    if mode == "serve":
        host = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SERVE_HOST
        try:
            port = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_SERVE_PORT
        except ValueError:
            print("usage: crm_provider.py serve [host] [port]", file=sys.stderr)
            sys.exit(2)
        sys.exit(serve(host, port))
    print(
        "usage: crm_provider.py [register|update|enroll [pattern]|run|"
        "serve [host] [port]|client <action_id> [request JSON]]",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

