# Grok2API v3.1.5 Custom Image Upgrade Design

## Decision

Upgrade production from upstream commit `86ae6057` to the tagged `v3.1.5`
release. Build a custom image from a clean `v3.1.5` branch in GitHub Actions and
deploy that image by immutable digest. The production host must not compile the
frontend, backend, dependencies, or container image.

The custom release is named `v3.1.5-aurora.1`. It carries only the approved
production behavior and reproducible deployment assets. It does not merge the
old production branch wholesale.

## Goals

- Retain all existing Grok2API account, key, configuration, audit, and media
  data.
- Retain Creative Console browser conversation history under the existing
  origin and `localStorage` key.
- Retain the separate SubBoost chat application and its PostgreSQL data.
- Make Web Search and X Search enabled and reasoning effort `xhigh` by default
  in Creative Console.
- Keep the DEEIX Chat promotion hidden.
- Inject the exact contents of `/root/grok.md` into all supported conversation
  protocols without damaging SSE streaming behavior.
- Keep the public API URL, Caddy domains, authentication mapping, GrokSearch,
  and MCP routing unchanged.
- Replace the fragile production frontend bundle overlays with a source-built
  custom image.

## Non-Goals

- Do not include the abandoned Console capacity-stream failover branch or its
  design and plan commits.
- Do not update beyond the `v3.1.5` tag to later untagged `main` commits.
- Do not update SubBoost, GrokSearch, Caddy, or their dependencies.
- Do not change credentials, account selection policy, model aliases, or the
  contents of `/root/grok.md`.
- Do not retain old hash-specific JavaScript bundles, the old entry bootstrap,
  or the canonical `index-DVIk9Mqh.js` cache workaround.

## Source Changes

### Creative Console Defaults

The Creative Console source must use these effective defaults:

- `reasoningEffort: "xhigh"`
- `webSearch: true`
- `xSearch: true`

The defaults apply on initial load, New Conversation, Clear Conversation,
history restoration, and history selection. A manual change applies to the
currently open conversation only and may be reset by those lifecycle events.

The fixed-reasoning Grok Console model
`grok-4.20-0309-reasoning` remains an exception: its effective effort is
`auto`, because upstream does not accept a configurable effort for that model.

Stored conversation messages, titles, timestamps, model selection, and prompt
cache keys must remain intact. Parsing old history may normalize only the three
default controls; it must not delete or rewrite message content.

### Promotion Removal

Remove the DEEIX Chat promotion from the Creative Console JSX. The custom image
must not depend on a CSS selector injected into a host-mounted `index.html`.
README sponsorship content is outside the deployed UI and is not modified.

### System Instruction Injection

Retain the existing protocol-aware Python proxy and its tests as deployment
assets in the fork. Production continues to run it as a constrained systemd
service on `127.0.0.1:8001`, loading `/root/grok.md` through a systemd
credential.

Caddy routes only these requests through the proxy:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`

All other Grok2API routes continue directly to `127.0.0.1:8000`. The proxy
prepends or sets the fixed instruction according to each protocol, preserves
authorization, never logs request bodies or the instruction, fails closed on
invalid input, and forwards SSE chunks without buffering.

Updating this release does not inspect or edit `/root/grok.md`. Restarting the
proxy reloads its exact current bytes.

### Public API URL

Keep `https://grok2api.xiaotianyo.com` as the effective public API base URL in
the production configuration. Use the `v3.1.5` runtime/configuration facility;
do not hardcode the domain into application source.

## Image Build And Publication

The branch is based directly on tag `v3.1.5`. GitHub Actions runs the upstream
backend tests, vet, Swagger verification, frontend lint, frontend build, and
multi-architecture Docker build. No equivalent full build runs on the
production host.

Publish the result from the Aurora fork as
`ghcr.io/aurora-new/grok2api:v3.1.5-aurora.1`. Before deployment, resolve the
amd64 image to a digest and pin that digest in production. Do not deploy a
mutable `latest` tag.

## Production Configuration

The production Compose overlay will stop mounting the old HTML and hashed
JavaScript files into `/app/frontend/dist`. The new image owns the complete,
internally consistent frontend build.

The following remain mounted or external exactly as production data and
configuration:

- `/root/grok2api-v3/config.yaml`
- `grok2api-v3_grok2api-data`
- `grok2api-v3_quality_guard_state`
- `/root/grok.md`
- the Caddy configuration and authentication map
- the GrokSearch systemd service
- the SubBoost containers and `subboost_subboost-local-db`

Remove the Caddy rule tied specifically to
`/assets/index-DVIk9Mqh.js`; the new image uses different hashed assets. Keep
the conversation routing, authorization forwarding, and `flush_interval -1`
behavior.

## Data Safety

Before changing the container, record the current image digest, Compose
configuration, service status, account count, and relevant volume identities.
Create a timestamped SQLite backup from the Grok2API data volume and validate
the backup with SQLite integrity checking. Do not delete or recreate either
Grok2API named volume.

Creative Console history is client-side. The `v3.1.5` source retains the same
`grok2api:creative-console:chat-history:` prefix and compatible message schema.
The deployment must retain the same HTTPS origin and must not clear browser
storage. A browser regression test seeds old-format history before loading the
new frontend and confirms that messages remain present.

SubBoost history is stored in its separate PostgreSQL volume. The Grok2API
upgrade must not recreate, migrate, or restart the SubBoost stack.

## Deployment And Verification

Before any image pull or container replacement, follow the host resource safety
check in `/root/AGENTS.md` and verify current production health. The server
pulls only the prebuilt image and never runs dependency installation or a cold
build.

Verification must cover:

- GitHub Actions tests and custom image publication succeed.
- The image reports the intended `v3.1.5` source and resolves to the recorded
  digest.
- Caddy configuration validates before reload.
- Grok2API becomes healthy and existing admin login, account count, client
  keys, models, settings, and media remain available.
- Existing Creative Console history loads with messages intact.
- Initial load, New Conversation, Clear Conversation, and history selection all
  show Web Search on, X Search on, and `xhigh`, subject to the fixed-model
  exception.
- The DEEIX Chat promotion is absent.
- Non-streaming and streaming requests work through every supported protocol.
- Streaming Web/X search activity appears progressively instead of arriving as
  one delayed block.
- The injected instruction is applied without emitting stray text such as a
  contract-check line.
- GrokSearch, MCP, Caddy, and SubBoost remain healthy.

## Rollback

Keep the old image digest, old Compose overlay, old frontend overlay files, and
the validated pre-upgrade database backup until the new release has completed
its observation window.

If only frontend or routing behavior fails before database writes become
relevant, restore the old image and old overlay. If the new backend migration
has made the database incompatible with the old binary, stop Grok2API and
restore the matching pre-upgrade database backup before starting the old
image. Restoring that backup discards Grok2API changes made after the upgrade,
so rollback should happen promptly if required. SubBoost data is never part of
this rollback.
