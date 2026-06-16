"""Example A2A requestor client for the LLM DMZ gateway."""

from __future__ import annotations

import json
import os
import sys
import uuid

from dotenv import load_dotenv
from python_a2a import A2AClient, Task, TaskState

load_dotenv()

GATEWAY_URL = os.getenv("A2A_DMZ_URL", "http://127.0.0.1:5000")
AGENT_ID = os.getenv("A2A_REQUESTOR_ID", "ext_agent")
AGENT_KEY = os.getenv("A2A_REQUESTOR_KEY", "ext-dev-key-change-me")


def submit(schema_id: str, payload: dict, request_id: str | None = None) -> Task:
    request_id = request_id or f"a2a-{uuid.uuid4().hex[:8]}"
    envelope = {
        "llmdmz": {
            "schema_id": schema_id,
            "request_id": request_id,
            "payload": payload,
        }
    }
    task = Task(
        id=request_id,
        metadata=envelope,
        message={"role": "user", "parts": [{"type": "data", "data": envelope}]},
    )
    client = A2AClient(
        GATEWAY_URL,
        headers={"X-Agent-Id": AGENT_ID, "X-Agent-Key": AGENT_KEY},
        google_a2a_compatible=True,
    )
    return client._send_task(task)


def main() -> None:
    schema_id = sys.argv[1] if len(sys.argv) > 1 else "crm_search"
    if schema_id == "crm_search":
        payload = {"company": "Acme Corp"}
    else:
        payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    result = submit(schema_id, payload)
    print(f"request_id={result.id}")
    print(f"state={result.status.state}")

    if result.status.state == TaskState.COMPLETED:
        response = (result.metadata or {}).get("llmdmz", {}).get("response_payload")
        print(json.dumps(response, indent=2))
    else:
        print(result.get_text())


if __name__ == "__main__":
    main()
