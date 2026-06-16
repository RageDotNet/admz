"""CLI for human reviewers to approve or reject DMZ queue items."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = os.getenv("LLMDMZ_URL", "http://127.0.0.1:8080")


def _headers(agent_id: str, agent_key: str) -> dict[str, str]:
    return {
        "X-Agent-Id": agent_id,
        "X-Agent-Key": agent_key,
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    path: str,
    *,
    agent_id: str,
    agent_key: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{DEFAULT_BASE_URL.rstrip('/')}{path}"
    response = requests.request(
        method,
        url,
        headers=_headers(agent_id, agent_key),
        json=payload,
        timeout=60,
    )
    if not response.ok:
        print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
        response.raise_for_status()
    return response.json()


def cmd_list(args: argparse.Namespace) -> None:
    data = _request(
        "GET",
        f"/api/v1/review/pending?limit={args.limit}",
        agent_id=args.agent_id,
        agent_key=args.agent_key,
    )
    reviews = data.get("reviews", [])
    if not reviews:
        print("No pending reviews.")
        return
    for item in reviews:
        print(
            f"{item['id']}  type={item['review_type']}  request={item['request_id']}\n"
            f"  reason: {item['reason']}\n"
            f"  payload: {json.dumps(item['payload_snapshot'], indent=2)}\n"
        )


def cmd_show(args: argparse.Namespace) -> None:
    data = _request(
        "GET",
        f"/api/v1/requests/{args.request_id}",
        agent_id=args.agent_id,
        agent_key=args.agent_key,
    )
    print(json.dumps(data, indent=2))


def cmd_approve(args: argparse.Namespace) -> None:
    payload = {"notes": args.notes} if args.notes else {}
    data = _request(
        "POST",
        f"/api/v1/review/{args.review_id}/approve",
        agent_id=args.agent_id,
        agent_key=args.agent_key,
        payload=payload,
    )
    print(json.dumps(data, indent=2))


def cmd_reject(args: argparse.Namespace) -> None:
    payload = {"notes": args.notes} if args.notes else {}
    data = _request(
        "POST",
        f"/api/v1/review/{args.review_id}/reject",
        agent_id=args.agent_id,
        agent_key=args.agent_key,
        payload=payload,
    )
    print(json.dumps(data, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM DMZ human review CLI")
    parser.add_argument("--agent-id", default=os.getenv("REVIEWER_AGENT_ID", "reviewer1"))
    parser.add_argument("--agent-key", default=os.getenv("REVIEWER_AGENT_KEY", "review-dev-key-change-me"))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)

    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="List pending review items")
    list_cmd.add_argument("--limit", type=int, default=50)
    list_cmd.set_defaults(func=cmd_list)

    show_cmd = sub.add_parser("show", help="Show request status")
    show_cmd.add_argument("request_id")
    show_cmd.set_defaults(func=cmd_show)

    approve_cmd = sub.add_parser("approve", help="Approve a review item")
    approve_cmd.add_argument("review_id")
    approve_cmd.add_argument("--notes")
    approve_cmd.set_defaults(func=cmd_approve)

    reject_cmd = sub.add_parser("reject", help="Reject a review item")
    reject_cmd.add_argument("review_id")
    reject_cmd.add_argument("--notes")
    reject_cmd.set_defaults(func=cmd_reject)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    global DEFAULT_BASE_URL
    DEFAULT_BASE_URL = args.base_url
    args.func(args)


if __name__ == "__main__":
    main()
