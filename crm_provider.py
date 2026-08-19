"""Trusted internal CRM provider for the LLM DMZ v2.

Two modes:

- ``python crm_provider.py register`` — publish the CRM actions
  (``crm_search``, ``crm_add_note``) as schema packages to the DMZ's
  agent-facing REST API (``POST /v2/actions``), using the schemas in
  ``./schemas``.

- ``python crm_provider.py run`` — implement the **exec delivery protocol**
  (dispatch-v2.md): read the unstructured framing on stdin, extract the
  request JSON after the ``REQUEST JSON FOLLOWS:`` marker, fulfill it, and
  write the response payload as JSON to stdout. Failures go to stderr with a
  non-zero exit code so the DMZ records them as failed attempts.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from crmtool import add_contact_note, search_contacts

# Provider bearer key (agent must carry the provider capability). Override
# with DMZ_PROVIDER_KEY when the key is reissued.
PROVIDER_KEY = os.getenv("DMZ_PROVIDER_KEY", "dmz_dtLE62fWaxmMBZ2QzBabmPJwlWf9jVglTMAYe1_RjLY")
DMZ_BASE_URL = os.getenv("DMZ_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

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
    with (SCHEMA_DIR / f"{name}.json").open(encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _action_package(action_id: str, description: str, provider_instructions: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "description": description,
        "request_schema": _load_schema(f"{action_id}_request"),
        "response_schema": _load_schema(f"{action_id}_response"),
        "provider_instructions": provider_instructions,
    }


ACTION_PACKAGES = [
    _action_package(
        "crm_search",
        "Query CRM contacts by customer name and/or company name. Returns the "
        "matching contact records, or an empty list if none matched.",
        "The request JSON contains optional 'name' and/or 'company' fields. "
        "Return {\"records\": [...]} with every matching contact; return an "
        "empty list when nothing matches. Output ONLY the response JSON.",
    ),
    _action_package(
        "crm_add_note",
        "Append a note to an existing CRM contact record. Returns the updated "
        "contact record.",
        "The request JSON contains 'contact_id' and 'note'. Append the note "
        "to that contact and return {\"record\": {...}} of the updated "
        "contact. Output ONLY the response JSON.",
    ),
]


def register() -> int:
    """POST each schema package to /v2/actions with the provider key."""
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


def run() -> int:
    framing = sys.stdin.read()
    try:
        payload = _extract_request_payload(framing)
        action_id = _infer_action_id(payload)
        response_payload = HANDLERS[action_id](payload)
    except Exception as exc:  # noqa: BLE001 — any failure is a failed attempt
        print(f"crm_provider: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(response_payload, ensure_ascii=False))
    return 0


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "register":
        sys.exit(register())
    if mode == "run":
        sys.exit(run())
    print("usage: crm_provider.py [register|run]", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()

