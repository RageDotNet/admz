# OpenClaw as a chat-completions provider

Configure an [OpenClaw](https://docs.openclaw.ai/) Gateway so Agent DMZ can dispatch to it with **OpenAI-compatible chat completions**. OpenClaw’s HTTP contract is [OpenAI chat completions](https://docs.openclaw.ai/gateway/openai-http-api). Delivery fields and retries are specified in [`dispatch-v2.md`](dispatch-v2.md).

If the DMZ and OpenClaw share a host, **Local command (exec)** is also viable: a script on stdin/stdout that runs `openclaw agent`. This page is the HTTP completions path.

## Enable the endpoint on the Gateway

Chat completions is **off by default**. In the OpenClaw config:

```json5
{
  gateway: {
    http: {
      endpoints: {
        chatCompletions: { enabled: true },
      },
    },
  },
}
```

The Gateway serves `/v1/chat/completions` (and `/v1/models`) on the same port as the rest of the Gateway. OpenClaw examples use `http://127.0.0.1:18789`. On a tailnet or reverse proxy the origin is `https://…`.

The DMZ **Endpoint URL** is the full completions path, not the `/v1` base:

```
https://gateway.example.ts.net/v1/chat/completions
```

Same host as `dmz-serve`:

```
http://127.0.0.1:18789/v1/chat/completions
```

Check that auth works from a machine that can reach the Gateway:

```
curl -sS https://gateway.example.ts.net/v1/models -H "Authorization: Bearer YOUR_GATEWAY_TOKEN"
```

A successful body lists agent targets such as `openclaw/default` and `openclaw/<agentId>`. Use one of those as the DMZ **Model** field.

## Gateway token

OpenClaw treats a valid Gateway token or password on this endpoint as **full operator access**. Requests run as a normal Gateway agent run. Keep the endpoint on loopback, a tailnet, or other private ingress.

| Gateway `gateway.auth.mode` | Header on the provider |
|---|---|
| `token` | `Authorization` = `Bearer <gateway.auth.token or OPENCLAW_GATEWAY_TOKEN>` |
| `password` | `Authorization` = `Bearer <gateway.auth.password or OPENCLAW_GATEWAY_PASSWORD>` |
| `none` (private ingress only) | omit the header |
| `trusted-proxy` | identity headers from the proxy; the DMZ is usually the wrong caller for that mode |

Store the bearer value only in the agent’s delivery headers in `/admin`. Those values live in the database and are never returned on `/v2`. Do not put them in git or `config.yaml`.

## Provider delivery in Agent DMZ

In `/admin` → **Agents**, register (or open) a **Provider** agent and set delivery **before** invoke so you can use **Test delivery connection**.

| Console field | Value |
|---|---|
| Delivery method | **OpenAI-compatible chat completions** |
| Endpoint URL | Full `…/v1/chat/completions` URL the DMZ process can reach |
| Headers | `Authorization` → `Bearer <gateway token or password>` |
| Model | An OpenClaw agent target from `GET /v1/models`, typically `openclaw/<agentId>` |
| Timeout / retries | Blank for defaults (180s / 2) unless the Gateway needs longer |

OpenClaw treats `model` as an **agent target**, not a raw upstream id such as `gpt-4o`. The DMZ copies the configured name into the JSON `model` field unchanged.

| Model | Routes to |
|---|---|
| `openclaw` or `openclaw/default` | Configured default Gateway agent |
| `openclaw/<agentId>` | That agent |

To override the agent’s backend model, add OpenClaw’s `x-openclaw-model` header. Shared-secret bearer callers may set it; extra headers are sent verbatim.

**Save the form** before testing. The test button uses last-saved settings, not unsaved edits.

If this agent also publishes actions via `/v2`, copy the reveal-once DMZ key when it is shown. That key is for Agent DMZ, not for OpenClaw.

### Reachability from Docker

The URL must resolve **from the process that runs Agent DMZ**, not from your browser.

| Where the Gateway listens | Where the DMZ runs | Typical endpoint |
|---|---|---|
| Same host, port 18789 | `dmz-serve` on the host | `http://127.0.0.1:18789/v1/chat/completions` |
| Same host | Compose (`deploy/docker-compose.yml`) on Windows/Mac | `http://host.docker.internal:18789/v1/chat/completions` |
| Tailnet or private HTTPS | Host or container that can route there | `https://gateway.example.ts.net/v1/chat/completions` |

`127.0.0.1` inside a container is the container, not the host. A hostname that only exists on your tailnet works if the container (or host) is on that network.

## Test the connection

On the provider form, **Test delivery connection**. The DMZ POSTs a short chat completion asking the model to echo a probe token, using the saved endpoint, model, and headers.

- Success: HTTP 200, a parseable completions body, and the probe token in the reply.
- Failure: HTTP status, response body, and exception chain. A Gateway that is up but rejecting auth often returns **403**; a disabled endpoint or wrong path fails differently from a bad token.

The **Tools** tab probes the LiteLLM **arbiter**, not OpenClaw.

## After delivery works

Same loop as any other provider ([README](../README.md) walkthrough): publish an action, approve it in **Directory**, enroll a client, invoke. Dispatch is a non-streaming completions request: system message = action instructions plus response schema; user message = the request JSON. The first choice’s `message.content` must be JSON that satisfies the action’s response schema. OpenClaw may use tools internally; the DMZ only accepts the final message content, not a `tool_calls` finish.

Raise **timeout** if the Gateway’s agent loop is routinely longer than 180 seconds. Worst-case invoke time is `timeout × (retries + 1)`.

## Same-host exec

When Agent DMZ and OpenClaw run on the same machine, you can set delivery to **Local command (exec)** and run a wrapper that calls `openclaw agent`. The DMZ writes unstructured framing to stdin (instructions, response schema, then `REQUEST JSON FOLLOWS:` and the payload) and reads JSON from stdout. Completions still need the HTTP endpoint above; exec does not.

`exec` runs **inside the DMZ process environment**. A command on the host is not visible to a container-only DMZ unless the image and volume layout expose it.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Connection refused / timeout | URL host and port from the DMZ’s network; Compose vs host; tailnet routing |
| HTTP 401 / 403 | Token or password matches `gateway.auth`; `Bearer ` prefix; chat completions enabled |
| HTTP 404 | Path is `/v1/chat/completions`, not `/v1` or `/v1/responses` |
| `GET /v1/models` works, delivery test fails | Model id is an agent target that exists; endpoint is the completions path |
| 200 but “not a parseable chat-completions body” | Gateway returned HTML or an error page; inspect the test result body |
| Live invoke `provider_failed` after a green test | Action schemas / arbiter, not connectivity; see the request log |

## Beyond the scope of this document

- OpenClaw Gateway install, pairing, operator scopes, streaming, and the `openclaw agent` CLI — see [OpenClaw’s chat completions page](https://docs.openclaw.ai/gateway/openai-http-api) and its security / remote-access docs.
- Client `/v2` wire format — [`rest-api-v2.md`](rest-api-v2.md).
- Using OpenClaw as a **client** of Agent DMZ (calling `/v2` with a `dmz_…` key) — that is the inverse role and does not use this delivery form.
