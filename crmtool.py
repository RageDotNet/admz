"""Mock CRM contact store used by crm_provider.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CRM_DATA_PATH = Path(__file__).parent / "data" / "crm.json"

MOCK_CONTACTS: list[dict[str, Any]] = [
    {
        "id": "c001",
        "name": "Jane Smith",
        "email": "jane.smith@acmecorp.com",
        "company": "Acme Corp",
        "phone": "+1-555-0101",
        "status": "active",
        "notes": "Enterprise renewal due Q3. Primary decision maker.",
    },
    {
        "id": "c002",
        "name": "Robert Chen",
        "email": "rchen@northwind.io",
        "company": "Northwind Analytics",
        "phone": "+1-555-0142",
        "status": "lead",
        "notes": "Requested demo after webinar. Interested in API integration.",
    },
    {
        "id": "c003",
        "name": "Maria Garcia",
        "email": "maria.g@globex.example",
        "company": "Globex Industries",
        "phone": "+1-555-0199",
        "status": "active",
        "notes": "Support escalation resolved 2025-11. Account in good standing.",
    },
    {
        "id": "c004",
        "name": "David Okonkwo",
        "email": "d.okonkwo@initech.com",
        "company": "Initech",
        "phone": "+1-555-0177",
        "status": "churned",
        "notes": "Left for competitor in Jan. Win-back campaign scheduled.",
    },
]


class CRM:
    def __init__(self, path: Path = CRM_DATA_PATH) -> None:
        self.path = path
        self._ensure_data()

    def _ensure_data(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({"contacts": MOCK_CONTACTS})

    def _read(self) -> dict[str, Any]:
        with self.path.open(encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def list_contacts(self) -> list[dict[str, Any]]:
        return self._read()["contacts"]

    def get_contact(self, contact_id: str) -> dict[str, Any] | None:
        for contact in self.list_contacts():
            if contact["id"] == contact_id:
                return contact
        return None

    def search_contacts(self, query: str) -> list[dict[str, Any]]:
        needle = query.lower()
        results = []
        for contact in self.list_contacts():
            haystack = " ".join(
                str(contact.get(field, ""))
                for field in ("name", "email", "company", "status", "notes")
            ).lower()
            if needle in haystack:
                results.append(contact)
        return results

    def add_note(self, contact_id: str, note: str) -> dict[str, Any]:
        data = self._read()
        for contact in data["contacts"]:
            if contact["id"] == contact_id:
                existing = contact.get("notes", "")
                contact["notes"] = f"{existing}\n{note}".strip() if existing else note
                self._write(data)
                return contact
        raise ValueError(f"Contact not found: {contact_id}")


crm = CRM()


def list_contacts() -> list[dict[str, Any]]:
    return crm.list_contacts()


def get_contact(contact_id: str) -> dict[str, Any] | None:
    return crm.get_contact(contact_id)


def search_contacts(query: str) -> list[dict[str, Any]]:
    return crm.search_contacts(query)


def add_contact_note(contact_id: str, note: str) -> dict[str, Any]:
    return crm.add_note(contact_id, note)


CRM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_contacts",
            "description": "List all contacts in the CRM.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contact",
            "description": "Get a single CRM contact by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "string",
                        "description": "Contact ID, e.g. c001",
                    }
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search CRM contacts by name, email, company, status, or notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_contact_note",
            "description": "Append a note to a CRM contact record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact ID"},
                    "note": {"type": "string", "description": "Note text to append"},
                },
                "required": ["contact_id", "note"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "list_contacts": lambda args: list_contacts(),
    "get_contact": lambda args: get_contact(args["contact_id"]),
    "search_contacts": lambda args: search_contacts(args["query"]),
    "add_contact_note": lambda args: add_contact_note(args["contact_id"], args["note"]),
}


def run_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name not in TOOL_HANDLERS:
        raise ValueError(f"Unknown tool: {name}")
    return TOOL_HANDLERS[name](arguments)
