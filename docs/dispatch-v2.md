# Dispatch v2 — DMZ-to-Provider Delivery

> Product requirements for the provider side of the wire: how the DMZ delivers a validated request to a provider and obtains a valid response. This document is self-contained. Companion documents: `system-prd-v2.md` (overall system and request pipeline), `rest-api-v2.md` (the client-facing invoke contract and error shapes), `schemas-v2.md` (schema registry, instruction fields), `webui-v2.md` (admin console, where provider delivery configuration is edited), `infra-v2.md` (stack and deployment).

## Overview & goals

When a client invokes an action, the DMZ validates the request and runs the arbiter; then it must **dispatch** — hand the request to the provider that owns the action — and get back a response it can validate, arbitrate, and return to the client. This document defines that half of the wire: how the provider's endpoint is configured, how the input is framed for each protocol type, and how timeouts, retries, and failures are handled.

Everything north of dispatch is `rest-api-v2.md`'s synchronous invoke contract; everything in this document happens inside that one client round trip.

Goals:

- **One endpoint per provider** — a provider agent has a single delivery configuration; all of that provider's actions are served through it.
- **Protocol-typed delivery** — `post`, `exec`, and `completions` cover the three realistic provider shapes: an HTTP service, a local command, and an LLM endpoint.
- **Retry with feedback** — when an attempt produces an invalid response, the retry carries the previous error back to the provider so it can self-correct, mirroring how the DMZ treats clients.
- **Bounded duration** — timeout and retry counts are finite and configured, so the synchronous invoke completes (or fails) within a known worst case.

## Provider delivery configuration

Each provider agent record carries a **delivery configuration**, set by an administrator in the console (`webui-v2.md`):

| Field | Applies to | Meaning |
|---|---|---|
| `protocol` | all | One of `post`, `exec`, `completions` |
| `endpoint` | `post`, `completions` | URL the DMZ calls |
| `command` | `exec` | Command line the DMZ runs as a local subprocess |
| `headers` | `post`, `completions` | Arbitrary HTTP headers passed through verbatim (e.g. `Authorization: Bearer ...` or any provider-specific auth) |
| `timeout` | all | Per-attempt timeout in seconds; **default 180** |
| `retries` | all | Maximum retries after a failed attempt; **default 2** |

Authentication to provider endpoints is **not a built-in system**. The DMZ does not manage credentials, tokens, or handshakes; whatever the provider's endpoint expects is expressed as configured headers and passed through as-is. The stored configuration (including header values) is treated as sensitive and protected at rest per `infra-v2.md`.

The 180-second default reflects the expected workload: a provider invocation commonly chains multiple tool invocations of its own, so dispatch calls are long-running by design.

## Input framing

The validated request JSON, the action's instructions, and the response schema are combined into the input the provider receives. The framing depends on the protocol.

### Unstructured framing (`post`, `exec`)

A single plain-text payload:

```
(the instructions)

(any error messages from the previous invocation if this is a retry triggered by validation failure)

(the schema to use for a response)

REQUEST JSON FOLLOWS:
(the request json)
```

- The **instructions** are the action's provider-facing instruction fields (`schemas-v2.md`).
- The **error block** is present only on retries; it carries the previous attempt's validation errors or arbiter verdict so the provider can correct its output.
- The **response schema** tells the provider what shape to produce.
- Everything after `REQUEST JSON FOLLOWS:` is the request payload, exactly as validated.

### Structured framing (`completions`)

The chat-completions API's native split:

- **System prompt** — the action's instructions and the response schema definition.
- **User prompt** — the request JSON.

On retry, the previous attempt's response and its validation/arbitration errors are appended to the conversation (an assistant turn with the failed response, followed by a user turn describing the errors), letting the model self-correct.

## Protocol types

### `post`

The DMZ sends an HTTP POST to the configured `endpoint` with the configured `headers` and the unstructured payload as the request body. The response body is the candidate response.

- HTTP 2xx → the body is a candidate; anything else is a failed attempt.
- The body must parse as JSON and satisfy the action's response schema.

### `exec`

The DMZ runs the configured `command` as a **local subprocess on the DMZ host** (`subprocess.Popen`). The entire unstructured payload is written to the process's **stdin**; the candidate response is read from **stdout**.

- Exit code 0 with parseable, schema-valid stdout → candidate response.
- Non-zero exit, unparseable stdout, or timeout → failed attempt; stderr is captured for the request log.
- The subprocess gets no network or filesystem restrictions; see the security section for the trust model this implies.

### `completions`

The DMZ calls the configured `endpoint` (an OpenAI-style chat-completions API) with the structured framing above. The candidate response is extracted from the completion's message content and must parse as JSON satisfying the action's response schema.

## Timeouts, retries, and failure taxonomy

Each dispatch attempt is bounded by the configured `timeout` (default 180s). An attempt **fails** when any of the following occurs:

| Failure | Examples | Retryable |
|---|---|---|
| Transport error | connection refused/reset, DNS failure, process spawn failure | Yes |
| Timeout | attempt exceeded `timeout` seconds | Yes |
| Protocol error | non-2xx HTTP status; non-zero process exit | Yes |
| Invalid response | unparseable JSON or response-schema violation | Yes |
| Rejected response | schema-valid but arbiter-rejected | Yes |

Every failure is retryable: the DMZ re-dispatches up to the configured `retries` (default 2), injecting the previous attempt's error into the next input (see Input framing). When all attempts are exhausted, the client receives the `provider_failed` error (`502`, shape in `rest-api-v2.md`) — the client is told the provider failed, not the details of the provider's output.

Worst-case synchronous invoke duration is `timeout × (retries + 1)` — up to ~9 minutes at defaults. This bound is deliberate and must be respected by the HTTP server's own timeouts (`infra-v2.md`).

## Response adjudication recap

For every attempt, the candidate response goes through the same pipeline as the client's request did: JSON/schema validation against the action's active response schema, then the LLM arbiter with the action's arbiter instructions. Only a fully valid, approved response is delivered to the client. This is a recap of `system-prd-v2.md`'s pipeline; this document adds only the attempt/retry mechanics around it.

## Observability

Each dispatch attempt is individually recorded in the request log (`system-prd-v2.md`, `webui-v2.md`):

- Timestamps (dispatch start, response received, total attempt duration)
- The exact input framing sent (unstructured payload or system/user prompts)
- Outcome: delivered, transport/timeout/protocol error, validation failure (with errors), or arbiter rejection (with verdict)
- For `exec`: exit code and captured stderr
- Attempt number and final retry count for the invocation

Nothing in dispatch waits on a human; the log is observational.

## Security posture

- **Provider outputs are untrusted.** Regardless of protocol, everything a provider returns goes through schema validation and arbitration before reaching a client. The provider cannot bypass this by any response content.
- **`exec` grants local code execution on the DMZ host — a deliberate design decision.** A provider with the `exec` protocol can run arbitrary code on the host that runs the DMZ. There is no sandbox, container, or resource limit around the subprocess in this version. This is acceptable because the trust boundary is *who becomes a provider*, not *what the process can do*: three independent human gates precede any `exec` dispatch — an administrator registers the provider agent and sets its delivery configuration, an administrator approves the action, and an administrator approves each client's enrollment. A registered provider is therefore **semi-trusted**: its outputs are treated as untrusted (validated and arbitrated), but its local processes are trusted by necessity of this design. The system explicitly does not claim isolation from a malicious trusted provider, who could access the database, keys, or other secrets on the host.
- **Configuration is sensitive.** Delivery configurations (including header values that carry credentials) are admin-managed and protected at rest; they are never returned to agents through the REST API.
- **Long timeouts are bounded.** Timeouts and retry counts are finite and configured, so a hung provider cannot hold a client connection or a worker indefinitely.

## Beyond the scope of this document

- **Sandboxing or containerization of `exec`** — a candidate future hardening item; explicitly out of scope for this version.
- **Client-facing invoke contract** — request/response shapes, error envelopes, and status codes live in `rest-api-v2.md`.
- **Arbiter internals** — prompt construction, model selection, and verdict parsing are system-level concerns (`system-prd-v2.md`).
- **Health checks, circuit breakers, and per-provider SLAs** — dispatch is per-invocation stateless; provider availability trends are observable only through the request log.
- **Streaming delivery** — responses are delivered whole, after validation.

