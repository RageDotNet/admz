"""Mock email inbox/outbox for the external LLM agent."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any

EMAILS_DIR = Path(__file__).parent / "emails"
EMAILS_OUT_DIR = Path(__file__).parent / "emails_out"
SEEN_STATE_PATH = Path(__file__).parent / "data" / "email_seen.json"

MOCK_INBOX: list[dict[str, str]] = [
    {
        "filename": "20250610T090000_Quarterly_newsletter.txt",
        "from": "news@industryweekly.example",
        "to": "agent@company.example",
        "subject": "Quarterly newsletter",
        "date": "2025-06-10T09:00:00Z",
        "body": (
            "Hi,\n\n"
            "This week's top stories in SaaS and enterprise software.\n"
            "No action required.\n"
        ),
    },
    {
        "filename": "20250612T141500_Meeting_follow_up.txt",
        "from": "partner@vendorco.example",
        "to": "agent@company.example",
        "subject": "Meeting follow-up",
        "date": "2025-06-12T14:15:00Z",
        "body": (
            "Thanks for the call yesterday.\n\n"
            "Can you confirm whether next week's integration workshop still works "
            "for your team?\n"
        ),
    },
    {
        "filename": "20250614T083000_Invoice_reminder.txt",
        "from": "billing@cloudhost.example",
        "to": "agent@company.example",
        "subject": "Invoice reminder",
        "date": "2025-06-14T08:30:00Z",
        "body": (
            "Reminder: invoice #8842 is due in 5 days.\n"
            "Reply if you need a copy resent.\n"
        ),
    },
]


def _sanitize_subject(subject: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", subject.strip())
    return cleaned.strip("_") or "no_subject"


def _format_email(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    date: str | None = None,
) -> str:
    sent_at = date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"From: {from_addr}\n"
        f"To: {to_addr}\n"
        f"Subject: {subject}\n"
        f"Date: {sent_at}\n"
        f"\n"
        f"{body.rstrip()}\n"
    )


def _parse_email(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    headers: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False

    for line in text.splitlines():
        if not in_body and not line.strip():
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    return {
        "filename": path.name,
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "body": "\n".join(body_lines).strip(),
    }


class EmailTool:
    def __init__(
        self,
        inbox_dir: Path = EMAILS_DIR,
        outbox_dir: Path = EMAILS_OUT_DIR,
        seen_path: Path = SEEN_STATE_PATH,
    ) -> None:
        self.inbox_dir = inbox_dir
        self.outbox_dir = outbox_dir
        self.seen_path = seen_path
        self._ensure_inbox()

    def _ensure_inbox(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.seen_path.parent.mkdir(parents=True, exist_ok=True)

        if not any(self.inbox_dir.iterdir()):
            for message in MOCK_INBOX:
                path = self.inbox_dir / message["filename"]
                path.write_text(
                    _format_email(
                        from_addr=message["from"],
                        to_addr=message["to"],
                        subject=message["subject"],
                        body=message["body"],
                        date=message["date"],
                    ),
                    encoding="utf-8",
                )

        if not self.seen_path.exists():
            self._write_seen(set())

    def _read_seen(self) -> set[str]:
        with self.seen_path.open(encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("seen", []))

    def _write_seen(self, seen: set[str]) -> None:
        with self.seen_path.open("w", encoding="utf-8") as f:
            json.dump({"seen": sorted(seen)}, f, indent=2)

    def _inbox_files(self) -> list[Path]:
        return sorted(
            path
            for path in self.inbox_dir.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )

    def get_new_emails(self) -> list[dict[str, Any]]:
        seen = self._read_seen()
        new_messages: list[dict[str, Any]] = []

        for path in self._inbox_files():
            if path.name in seen:
                continue
            new_messages.append(_parse_email(path))
            seen.add(path.name)

        if new_messages:
            self._write_seen(seen)

        return new_messages

    def list_inbox(self) -> list[dict[str, Any]]:
        return [_parse_email(path) for path in self._inbox_files()]

    def get_email(self, filename: str) -> dict[str, Any] | None:
        path = self.inbox_dir / filename
        if not path.is_file():
            return None
        return _parse_email(path)

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        from_addr: str = "agent@company.example",
    ) -> dict[str, str]:
        _, to_addr = parseaddr(to)
        if not to_addr:
            raise ValueError(f"Invalid recipient: {to}")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"{timestamp}_{_sanitize_subject(subject)}.txt"
        path = self.outbox_dir / filename
        path.write_text(
            _format_email(
                from_addr=from_addr,
                to_addr=to_addr,
                subject=subject,
                body=body,
            ),
            encoding="utf-8",
        )
        return {
            "filename": filename,
            "to": to_addr,
            "subject": subject,
            "status": "sent",
        }


email_tool = EmailTool()


def get_new_emails() -> list[dict[str, Any]]:
    return email_tool.get_new_emails()


def list_inbox() -> list[dict[str, Any]]:
    return email_tool.list_inbox()


def get_email(filename: str) -> dict[str, Any] | None:
    return email_tool.get_email(filename)


def send_email(
    to: str,
    subject: str,
    body: str,
    from_addr: str = "agent@company.example",
) -> dict[str, str]:
    return email_tool.send_email(to=to, subject=subject, body=body, from_addr=from_addr)


EMAIL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_new_emails",
            "description": (
                "Scan the inbox and return emails that have not been fetched before."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_inbox",
            "description": "List all emails currently in the inbox.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email",
            "description": "Read a specific inbox email by filename.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Inbox filename, e.g. 20250610T090000_Quarterly_newsletter.txt",
                    }
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email. The message is written to the outbox as a mock send.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                    "from_addr": {
                        "type": "string",
                        "description": "Optional sender address",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "get_new_emails": lambda args: get_new_emails(),
    "list_inbox": lambda args: list_inbox(),
    "get_email": lambda args: get_email(args["filename"]),
    "send_email": lambda args: send_email(
        to=args["to"],
        subject=args["subject"],
        body=args["body"],
        from_addr=args.get("from_addr", "agent@company.example"),
    ),
}


def run_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name not in TOOL_HANDLERS:
        raise ValueError(f"Unknown tool: {name}")
    return TOOL_HANDLERS[name](arguments)
