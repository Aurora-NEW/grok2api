# Global System Instruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject `/root/grok.md` into every production conversational request without rebuilding grok2api.

**Architecture:** A Python standard-library proxy on loopback port 8001 performs protocol-aware JSON rewriting and streams the response from grok2api on port 8000. Caddy routes only public conversational POSTs to it, while GrokSearch uses it as its API base.

**Tech Stack:** Python 3.12 standard library, `unittest`, systemd 255, Caddy, Bash verification scripts

---

### Task 1: Protocol Rewriter Tests

**Files:**
- Create: `scripts/test_system_instruction_proxy.py`
- Create: `scripts/system_instruction_proxy.py`

- [ ] **Step 1: Write failing transform tests**

Cover Chat Completions message prepending, Responses instruction merging, Anthropic string and block forms, invalid JSON, invalid shapes, compressed requests, and the 32 MiB limit. Import `inject_instruction` from the not-yet-created module.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest scripts/test_system_instruction_proxy.py -v`

Expected: import failure because `scripts/system_instruction_proxy.py` does not exist.

- [ ] **Step 3: Implement minimal transforms**

Create `inject_instruction(path: str, body: bytes, instruction: str) -> bytes` using `json.loads` and compact `json.dumps`, with fixed text placed before client instructions.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest scripts/test_system_instruction_proxy.py -v`

Expected: all transform tests pass.

### Task 2: Streaming Reverse Proxy

**Files:**
- Modify: `scripts/test_system_instruction_proxy.py`
- Modify: `scripts/system_instruction_proxy.py`

- [ ] **Step 1: Write failing HTTP integration tests**

Start an in-process capture upstream and proxy. Verify the rewritten body and authorization header received upstream, then verify both content-length JSON and chunked SSE responses reach the client unchanged.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest scripts/test_system_instruction_proxy.py -v`

Expected: failures because the HTTP proxy server is not implemented.

- [ ] **Step 3: Implement the proxy**

Use `ThreadingHTTPServer` and `http.client.HTTPConnection`, remove hop-by-hop headers, reframe chunked responses, flush streaming chunks, expose a loopback health path, avoid body logging, and return protocol-shaped 4xx/5xx errors.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest scripts/test_system_instruction_proxy.py -v`

Expected: all tests pass without warnings.

### Task 3: Production Service and Verification Assets

**Files:**
- Create: `deploy/grok-system-instruction-proxy.service`
- Create: `deploy/grok-system-instruction.caddy`
- Create: `scripts/verify-production-system-instruction.sh`

- [ ] **Step 1: Add deployment templates**

Define a hardened systemd unit that uses `LoadCredential=system-instruction:/root/grok.md`, a 32 MiB body limit, bounded parse concurrency, automatic restart, and resource limits. Document the Caddy matcher and two upstream routes.

- [ ] **Step 2: Add lightweight deployment verification**

Check systemd state, loopback health, Caddy validation, public health/models, authorization behavior, and GrokSearch's configured API port without printing credentials or the instruction.

- [ ] **Step 3: Validate local assets**

Run: `systemd-analyze verify deploy/grok-system-instruction-proxy.service`

Run: `bash -n scripts/verify-production-system-instruction.sh`

Expected: both commands exit 0.

### Task 4: Deploy and Smoke Test

**Files:**
- Modify: `/etc/caddy/Caddyfile`
- Create: `/etc/systemd/system/grok-system-instruction-proxy.service`
- Modify: `/root/GrokSearch/run-grok-search.sh`

- [ ] **Step 1: Record pre-deployment health**

Confirm the container, Caddy, GrokSearch, public health, model listing, active key, legacy key, and invalid-key rejection before routing changes.

- [ ] **Step 2: Install and start the proxy**

Install the tested script and unit, reload systemd, enable and start the service, then verify `http://127.0.0.1:8001/_system-instruction/health`.

- [ ] **Step 3: Switch traffic safely**

Validate the edited Caddyfile before reload. Route the three public POST paths to port 8001, keep all other traffic on port 8000, update GrokSearch to port 8001, and restart only GrokSearch.

- [ ] **Step 4: Run production verification**

Run the verification script plus a non-streaming request and an SSE request. Confirm proxy journal entries show injection for each path without logging content.

- [ ] **Step 5: Inspect final state**

Confirm service resource use, listen addresses, container health, Caddy health, GrokSearch health, and a clean repository worktree.
