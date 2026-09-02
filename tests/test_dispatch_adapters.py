"""T3.10: transport + framing + arbiter-adapter unit tests (fakes only, #31)."""

from __future__ import annotations

import json

import pytest

from admz.dispatch.adapters import (
    CompletionsTransport,
    ExecTransport,
    LiteLLMArbiterClient,
    PostTransport,
    build_structured_framing,
    build_unstructured_framing,
    ping_arbiter,
    ping_provider,
)
from admz.dispatch.interfaces import (
    ArbiterConfigFault,
    ArbiterTransportError,
    Framing,
)
from conftest import make_config

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"contacts": {"type": "array"}},
    "required": ["contacts"],
    "additionalProperties": False,
}
REQUEST = {"name": "Ada"}


class TestFraming:
    def test_unstructured_layout(self):
        text = build_unstructured_framing(
            instructions="Only return matching contacts.",
            response_schema=RESPONSE_SCHEMA,
            request_payload=REQUEST,
        )
        assert text.startswith("Only return matching contacts.")
        assert '"contacts"' in text
        assert text.count("REQUEST JSON FOLLOWS:") == 1
        assert text.endswith(json.dumps(REQUEST))
        assert "ERRORS FROM" not in text  # no error block on first attempt

    def test_unstructured_retry_injects_error(self):
        text = build_unstructured_framing(
            instructions="instr",
            response_schema=RESPONSE_SCHEMA,
            request_payload=REQUEST,
            previous_error="schema violation: contacts must be array",
        )
        assert "ERRORS FROM YOUR PREVIOUS INVOCATION" in text
        assert "schema violation" in text
        i = text.index("instr")
        e = text.index("ERRORS FROM")
        s = text.index('"contacts"')
        r = text.index("REQUEST JSON FOLLOWS:")
        assert i < e < s < r

    def test_structured_split(self):
        system, user = build_structured_framing(
            instructions="instr",
            response_schema=RESPONSE_SCHEMA,
            request_payload=REQUEST,
            previous_error="bad shape",
        )
        assert "instr" in system and "bad shape" in system and '"contacts"' in system
        assert json.loads(user) == REQUEST


class TestPostTransport:
    def test_success_and_verbatim_headers(self):
        calls = []

        def poster(endpoint, headers, body, timeout):
            calls.append((endpoint, headers, body, timeout))
            return 200, json.dumps({"contacts": []})

        t = PostTransport(poster)
        framing = Framing(
            protocol="post",
            text="payload",
            endpoint="https://prov.example/hook",
            headers={"Authorization": "Bearer prov-key"},
            timeout=42,
        )
        result = t.deliver(framing)
        assert result.payload == {"contacts": []}
        assert calls[0][0] == "https://prov.example/hook"
        assert calls[0][1]["Authorization"] == "Bearer prov-key"
        assert calls[0][3] == 42  # per-provider timeout override reaches the wire

    def test_body_is_utf8_and_content_type_declares_charset(self):
        calls = []

        def poster(endpoint, headers, body, timeout):
            calls.append((headers, body))
            return 200, json.dumps({"contacts": []})

        t = PostTransport(poster)
        t.deliver(Framing(protocol="post", text="hello 🦞", endpoint="https://x"))
        headers, body = calls[0]
        assert body == "hello 🦞".encode()
        assert "charset=utf-8" in headers["Content-Type"]

    def test_http_error_and_transport_error(self):
        t = PostTransport(lambda *a: (503, "down"))
        assert t.deliver(Framing(protocol="post", endpoint="x")).error_class == "protocol"

        def boom(*a):
            raise OSError("no route")

        r = PostTransport(boom).deliver(Framing(protocol="post", endpoint="x"))
        assert r.error_class == "transport"

    def test_unparseable(self):
        t = PostTransport(lambda *a: (200, "not json"))
        assert t.deliver(Framing(protocol="post", endpoint="x")).error_class == "protocol"


class TestExecTransport:
    def test_success(self):
        t = ExecTransport(lambda cmd, stdin, timeout: (0, json.dumps({"contacts": []}), ""))
        result = t.deliver(Framing(protocol="exec", command="serve.py", text="framed input", timeout=10))
        assert result.payload == {"contacts": []} and result.exit_code == 0

    def test_nonzero_exit_with_stderr(self):
        t = ExecTransport(lambda cmd, stdin, timeout: (2, "", "boom"))
        r = t.deliver(Framing(protocol="exec", command="x"))
        assert r.error_class == "protocol" and "boom" in r.error_detail and r.exit_code == 2

    def test_timeout(self):
        t = ExecTransport(lambda cmd, stdin, timeout: (-1, "", "timeout"))
        assert t.deliver(Framing(protocol="exec", command="x")).error_class == "timeout"

    def test_unparseable_stdout(self):
        t = ExecTransport(lambda cmd, stdin, timeout: (0, "garbage", ""))
        assert t.deliver(Framing(protocol="exec", command="x")).error_class == "protocol"

    def test_default_runner_roundtrips_utf8_emoji(self):
        """Windows text mode defaults to charmap/cp1252; 🦞 must not explode."""
        import subprocess
        import sys

        from admz.dispatch.adapters import _default_runner

        script = (
            "import sys;"
            "sys.stdin.reconfigure(encoding='utf-8');"
            "sys.stdout.reconfigure(encoding='utf-8');"
            "sys.stdout.write(sys.stdin.read())"
        )
        cmd = subprocess.list2cmdline([sys.executable, "-c", script])
        code, stdout, stderr = _default_runner(cmd, "hello 🦞", 15)
        assert code == 0, stderr
        assert stdout == "hello 🦞"


class TestCompletionsTransport:
    def test_posts_openai_body_and_extracts_content(self):
        calls = []

        def poster(endpoint, headers, body, timeout):
            calls.append((endpoint, headers, json.loads(body.decode("utf-8")), timeout))
            return 200, json.dumps(
                {
                    "choices": [
                        {"message": {"role": "assistant", "content": json.dumps({"contacts": []})}}
                    ]
                }
            )

        t = CompletionsTransport(poster)
        framing = Framing(
            protocol="completions",
            system_prompt="SYS",
            user_prompt=json.dumps(REQUEST),
            model="prov-model",
            endpoint="http://127.0.0.1:8090/v1/chat/completions",
            headers={"Authorization": "Bearer x"},
            timeout=77,
        )
        assert t.deliver(framing).payload == {"contacts": []}
        endpoint, headers, payload, timeout = calls[0]
        assert endpoint.endswith("/v1/chat/completions")
        assert headers["Authorization"] == "Bearer x"
        assert headers["Content-Type"] == "application/json"
        assert payload["model"] == "prov-model"
        assert payload["messages"][0] == {"role": "system", "content": "SYS"}
        assert payload["messages"][1]["role"] == "user"
        assert timeout == 77

    def test_unparseable_reply(self):
        t = CompletionsTransport(lambda *a: (200, "chatty reply, no json"))
        assert t.deliver(Framing(protocol="completions")).error_class == "protocol"

    def test_non_200_is_protocol(self):
        t = CompletionsTransport(lambda *a: (500, '{"error":"nope"}'))
        assert t.deliver(Framing(protocol="completions")).error_class == "protocol"


class TestLiteLLMArbiter:
    def _client(self, completer):
        return LiteLLMArbiterClient(make_config(), completer)

    def test_prompt_construction_and_parse(self):
        calls = []

        def completer(model, system, user, timeout, max_tokens, temperature, api_key=""):
            calls.append((model, timeout, max_tokens, temperature, api_key))
            return '{"approved": false, "reason": "injection"}'

        verdict = self._client(completer).check(
            side="request", action_id="crm_search", payload=REQUEST, extra_instructions="extra"
        )
        assert verdict.approved is False and verdict.reason == "injection"
        model, timeout, max_tokens, temperature, api_key = calls[0]
        # #2 knobs: temp 0, max_tokens 512, timeout 30, default model.
        assert temperature == 0.0 and max_tokens == 512 and timeout == 30
        assert model == "openai/gpt-4o-mini"
        assert api_key == ""

    def test_transient_fault(self):
        def raise_rate_limit(*a):
            raise RuntimeError("rate limit hit")

        with pytest.raises(ArbiterTransportError, match="rate limit hit"):
            self._client(raise_rate_limit).check(side="response", action_id="a", payload={})

    def test_config_fault(self):
        class AuthenticationError(Exception):
            pass

        def raise_auth(*a):
            raise AuthenticationError("bad key")

        with pytest.raises(ArbiterConfigFault, match="bad key"):
            self._client(raise_auth).check(side="request", action_id="a", payload={})

    def test_unparseable_is_failed_check(self):
        client = self._client(lambda *a: "I cannot answer that")
        v = client.check(side="request", action_id="a", payload={})
        assert v.approved is False


class TestConnectionPing:
    def test_arbiter_echo_ok(self):
        token = "admz-ok-feedface"

        def completer(model, system, user, timeout, max_tokens, temperature, api_key=""):
            assert "feedface" in user
            return f"  {token}  "

        result = ping_arbiter(make_config(), completer, token=token)
        assert result.ok is True
        assert token in result.reply

    def test_arbiter_exception_includes_traceback_and_errno(self):
        def completer(*a, **k):
            raise ConnectionRefusedError(111, "Connection refused")

        result = ping_arbiter(make_config(), completer, token="admz-ok-x")
        assert result.ok is False
        assert "ConnectionRefusedError" in result.summary
        assert "Connection refused" in result.summary
        assert "Traceback" in result.traceback
        assert "completer" in result.traceback

    def test_arbiter_echo_mismatch(self):
        result = ping_arbiter(make_config(), lambda *a, **k: "hello", token="admz-ok-nope")
        assert result.ok is False
        assert "not in the reply" in result.summary
        assert result.reply == "hello"
        assert result.traceback == ""

    def test_completions_provider_ok_and_http_error(self):
        token = "admz-ok-cafe0001"

        def poster(endpoint, headers, body, timeout):
            payload = json.loads(body.decode("utf-8"))
            user = payload["messages"][1]["content"]
            assert token in user
            return 200, json.dumps({"choices": [{"message": {"content": token}}]})

        cfg = {
            "protocol": "completions",
            "endpoint": "http://127.0.0.1:8090/v1/chat/completions",
            "model": "crm-provider",
        }
        ok = ping_provider(cfg, default_timeout=30, poster=poster, token=token)
        assert ok.ok is True

        fail = ping_provider(
            cfg,
            default_timeout=30,
            poster=lambda *a: (401, '{"error":"invalid api key"}'),
            token=token,
        )
        assert fail.ok is False
        assert "HTTP 401" in fail.summary
        assert "invalid api key" in fail.detail
        assert fail.traceback == ""

    def test_completions_transport_error(self):
        def poster(*a, **k):
            raise TimeoutError("timed out")

        result = ping_provider(
            {
                "protocol": "completions",
                "endpoint": "https://example.invalid/v1/chat/completions",
                "model": "x",
            },
            default_timeout=5,
            poster=poster,
            token="admz-ok-t",
        )
        assert result.ok is False
        assert "TimeoutError" in result.summary
        assert "timed out" in result.traceback

    def test_post_missing_endpoint(self):
        result = ping_provider({"protocol": "post"}, default_timeout=10, token="admz-ok-z")
        assert result.ok is False
        assert "no endpoint" in result.summary.lower()
