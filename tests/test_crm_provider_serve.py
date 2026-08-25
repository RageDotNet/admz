"""Offline tests for crm_provider.py serve (OpenAI-compatible completions)."""

from __future__ import annotations

import json

from crm_provider import SCHEMA_DIR, _load_schema, create_serve_app


def test_schemas_are_loaded_from_examples_directory():
    assert SCHEMA_DIR.is_dir()
    assert SCHEMA_DIR.parent.name == "examples"
    request = _load_schema("crm_search_request")
    assert request["title"] == "CRM Search Request"
    assert _load_schema("crm_add_note_request")["title"]


def test_chat_completions_search():
    client = create_serve_app().test_client()
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "crm-provider",
            "messages": [
                {"role": "system", "content": "return JSON"},
                {"role": "user", "content": json.dumps({"name": "Ada"})},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "crm-provider"
    payload = json.loads(body["choices"][0]["message"]["content"])
    assert "records" in payload


def test_chat_completions_alias_path():
    client = create_serve_app().test_client()
    resp = client.post(
        "/chat/completions",
        json={"messages": [{"role": "user", "content": '{"company": "Acme"}'}]},
    )
    assert resp.status_code == 200
    payload = json.loads(resp.get_json()["choices"][0]["message"]["content"])
    assert "records" in payload


def test_chat_completions_bad_payload_is_500():
    client = create_serve_app().test_client()
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": '{"nope": true}'}]},
    )
    assert resp.status_code == 500
    assert resp.get_json()["error"]["type"] == "server_error"


def test_chat_completions_requires_messages():
    client = create_serve_app().test_client()
    resp = client.post("/v1/chat/completions", json={"model": "x"})
    assert resp.status_code == 400
