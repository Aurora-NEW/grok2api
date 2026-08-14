# Global System Instruction Injection Design

## Goal

Inject the UTF-8 text from `/root/grok.md` before every client-provided system instruction for all production conversational requests, without rebuilding the grok2api image on the small production host.

## Scope

The policy applies to:

- OpenAI Chat Completions: `POST /v1/chat/completions`
- OpenAI Responses: `POST /v1/responses`
- Anthropic Messages: `POST /v1/messages`
- Creative Console, which uses `POST /v1/responses`
- GrokSearch, whose API base URL will point at the injection proxy

Media, model listing, authentication, admin, health, and static asset routes are not modified.

## Architecture

A small Python standard-library reverse proxy listens on `127.0.0.1:8001` and forwards to the existing grok2api container on `127.0.0.1:8000`. Caddy sends only the three public conversational POST routes through the proxy; all other public traffic continues to use port 8000 directly. GrokSearch uses port 8001 as its API base so its chat requests receive the same policy.

The systemd service loads `/root/grok.md` as a read-only credential at startup. The proxy never logs the instruction or request bodies. Updating the instruction requires restarting the service, which reloads the credential.

## Protocol Rewrites

- Chat Completions: prepend a `{ "role": "system", "content": <fixed text> }` item to `messages`.
- Responses: set `instructions` to the fixed text, or prepend the fixed text and a blank-line separator to an existing string value.
- Anthropic Messages: set `system` to the fixed text, prepend it to an existing string, or prepend a text block to an existing block array.

The client payload remains otherwise intact. Rewrites use the standard JSON parser and serializer. The proxy accepts at most 32 MiB, matching the current grok2api request limit.

## Failure Behavior

Injection is fail closed. Empty or invalid instruction files prevent the service from starting. Invalid JSON, unsupported compressed request bodies, invalid protocol shapes, and oversized bodies receive a local 4xx response rather than reaching grok2api without the fixed instruction. An unavailable proxy causes conversational endpoints and GrokSearch to fail instead of bypassing the policy.

The service has a restart policy, a concurrency cap, and systemd CPU/memory limits. Caddy continues serving the UI and non-conversation APIs if the injection service is unavailable.

## Verification

Targeted unit and integration tests cover all three protocol transforms, existing client instructions, invalid input, authorization forwarding, and chunked/SSE response streaming. Production verification covers service health, Caddy validation, unchanged model and admin health routes, active and legacy API keys, rejected invalid keys, one non-streaming request, one streaming request, and GrokSearch routing.

## Rollback

Restore Caddy's conversational routes to `127.0.0.1:8000`, restore GrokSearch's API URL to port 8000, then stop and disable `grok-system-instruction-proxy.service`. The grok2api container and data are not changed.
