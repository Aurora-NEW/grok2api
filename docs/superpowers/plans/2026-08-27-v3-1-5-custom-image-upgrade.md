# Grok2API v3.1.5 Custom Image Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution constraint:** The user has explicitly disabled subagents for this work. Use `superpowers:executing-plans` inline and stop at every production gate.

**Release revision:** Candidate `v3.1.5-aurora.1` is an immutable failed CI record: verification and both architecture builds passed, but `docker/metadata-action` generated an unintended `latest` tag that broke manifest assembly. Candidate `v3.1.5-aurora.2` disables automatic `latest` generation; all deployment paths below refer to `.2`. The production branch name remains `production-v3.1.5-aurora.1`.

**Goal:** Publish and deploy a pinned `v3.1.5` custom image that preserves production data, injects `/root/grok.md`, hides the DEEIX Chat promotion, and defaults Creative Console to Web Search on, X Search on, and `xhigh` reasoning.

**Architecture:** Start from the immutable upstream `v3.1.5` tag, implement the frontend behavior in source, and retain the existing instruction proxy as an external systemd/Caddy layer. GitHub Actions performs all dependency installation, tests, and image builds; the production host only runs lightweight source tests, pulls the verified image, validates a cloned SQLite database in a resource-limited canary, and recreates one container against the existing named volumes.

**Tech Stack:** React 19, TypeScript 6, Node test runner, Go 1.26, Python 3 standard library, Docker Compose, GitHub Actions/GHCR, SQLite, Caddy, systemd.

---

## File Map

- Create `frontend/src/features/creative-console/creative-console-defaults.ts`: one source of truth for the three chat defaults.
- Create `frontend/src/features/creative-console/creative-console-defaults.test.ts`: pure regression tests that preserve session payloads while overriding only the three controls.
- Modify `frontend/src/features/creative-console/creative-console-page.tsx`: consume the defaults in every conversation lifecycle and remove the promotion JSX.
- Create `scripts/test-creative-console-customizations.mjs`: dependency-free source wiring test runnable on this host's Node 18.
- Create `scripts/test_ghcr_workflow.py`: guard tag metadata against automatic `latest` collisions.
- Create `scripts/test_release_metadata.py`: keep verification and backup paths aligned with the current immutable release candidate.
- Restore `scripts/system_instruction_proxy.py` and `scripts/test_system_instruction_proxy.py`: protocol-aware fixed-instruction proxy and tests.
- Restore `deploy/grok-system-instruction-proxy.service`, `deploy/grok-system-instruction.caddy`, and `scripts/verify-production-system-instruction.sh`: reproducible deployed proxy configuration and smoke checks.
- Create `docker-compose.production.yml`: production container name only; no frontend asset bind mounts.
- Create `scripts/verify-production-custom-release.sh`: repeatable post-cutover health, image, volume, frontend, data, and companion-service checks.
- Modify `.github/workflows/ghcr-image.yml`: test the custom behavior and publish the exact production branch in the Aurora fork.
- Modify `.gitignore`: keep local worktrees out of status without importing the old production branch.
- Modify `/etc/caddy/Caddyfile` during deployment: replace the obsolete hashed-entry cache rule with HTML revalidation while retaining API routing.
- Modify `/root/grok2api-v3/.env.production` during deployment: pin the custom GHCR tag and manifest digest.

### Task 1: Add Failing Creative Console Regression Tests

**Files:**
- Create: `scripts/test-creative-console-customizations.mjs`
- Create: `frontend/src/features/creative-console/creative-console-defaults.test.ts`
- Test: `frontend/src/features/creative-console/creative-console-page.tsx`

- [ ] **Step 1: Add the dependency-free source contract test**

Create `scripts/test-creative-console-customizations.mjs` with:

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pageURL = new URL("../frontend/src/features/creative-console/creative-console-page.tsx", import.meta.url);
const source = readFileSync(pageURL, "utf8");

function section(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.ok(start >= 0, `${startMarker} is missing`);
  assert.ok(end > start, `${endMarker} must follow ${startMarker}`);
  return source.slice(start, end);
}

assert.doesNotMatch(source, /DEEIX Chat|DEEIX-AI\/DEEIX-Chat/);
assert.match(source, /from "@\/features\/creative-console\/creative-console-defaults"/);
assert.match(source, /grok2api:creative-console:chat-history:/);
assert.match(source, /grok-4\.20-0309-reasoning/);

const clearConversation = section("function clearConversation(): void {", "function startNewConversation(): void {");
assert.match(clearConversation, /setReasoningEffort\(blank\.reasoningEffort\)/);
assert.match(clearConversation, /setWebSearch\(blank\.webSearch\)/);
assert.match(clearConversation, /setXSearch\(blank\.xSearch\)/);

const newConversation = section("function startNewConversation(): void {", "function switchConversation(targetId: string): void {");
assert.match(newConversation, /setReasoningEffort\(blank\.reasoningEffort\)/);
assert.match(newConversation, /setWebSearch\(blank\.webSearch\)/);
assert.match(newConversation, /setXSearch\(blank\.xSearch\)/);

const switchConversation = section("function switchConversation(targetId: string): void {", "function handlePromptKeyDown");
assert.match(switchConversation, /const defaults = createCreativeChatDefaults\(\)/);
assert.match(switchConversation, /setReasoningEffort\(defaults\.reasoningEffort\)/);
assert.match(switchConversation, /setWebSearch\(defaults\.webSearch\)/);
assert.match(switchConversation, /setXSearch\(defaults\.xSearch\)/);
assert.doesNotMatch(switchConversation, /set(?:ReasoningEffort|WebSearch|XSearch)\(target\./);

const blankSession = section("function createBlankChatSession(model: string): ChatSession {", "function createChatSessionTitle");
assert.match(blankSession, /withCreativeChatDefaults\(\{/);

const parser = section("function parseChatSession(value: unknown): ChatSession[] {", "function parseConversationMessage");
assert.match(parser, /withCreativeChatDefaults\(\{/);
assert.match(parser, /messages/);
assert.match(parser, /promptCacheKey/);
assert.match(parser, /model:/);

console.log("Creative Console customization source tests passed");
```

- [ ] **Step 2: Add the pure defaults test before its module exists**

Create `frontend/src/features/creative-console/creative-console-defaults.test.ts` with:

```ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createCreativeChatDefaults, withCreativeChatDefaults } from "./creative-console-defaults.ts";

describe("Creative Console chat defaults", () => {
  it("returns Web and X search enabled with xhigh reasoning", () => {
    assert.deepEqual(createCreativeChatDefaults(), {
      reasoningEffort: "xhigh",
      webSearch: true,
      xSearch: true,
    });
  });

  it("overrides only controls while preserving stored conversation data", () => {
    const messages = [{ id: "message-1", role: "user", content: "keep me" }];
    const stored = {
      id: "session-1",
      model: "grok-chat-fast",
      promptCacheKey: "cache-1",
      messages,
      reasoningEffort: "auto",
      webSearch: false,
      xSearch: false,
    };

    const normalized = withCreativeChatDefaults(stored);

    assert.equal(normalized.id, stored.id);
    assert.equal(normalized.model, stored.model);
    assert.equal(normalized.promptCacheKey, stored.promptCacheKey);
    assert.equal(normalized.messages, messages);
    assert.equal(normalized.reasoningEffort, "xhigh");
    assert.equal(normalized.webSearch, true);
    assert.equal(normalized.xSearch, true);
    assert.equal(stored.reasoningEffort, "auto");
  });
});
```

- [ ] **Step 3: Run the lightweight test and prove the existing source fails**

Run:

```bash
node scripts/test-creative-console-customizations.mjs
```

Expected: FAIL with an assertion showing the DEEIX promotion or defaults import is still present/missing. Do not install frontend dependencies on this host.

### Task 2: Implement Source-Level Defaults And Promotion Removal

**Files:**
- Create: `frontend/src/features/creative-console/creative-console-defaults.ts`
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx:1-205`
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx:595-680`
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx:1780-1870`
- Test: `scripts/test-creative-console-customizations.mjs`
- Test: `frontend/src/features/creative-console/creative-console-defaults.test.ts`

- [ ] **Step 1: Add the defaults module**

Create `frontend/src/features/creative-console/creative-console-defaults.ts` with:

```ts
export type CreativeChatDefaults = {
  reasoningEffort: "xhigh";
  webSearch: true;
  xSearch: true;
};

export function createCreativeChatDefaults(): CreativeChatDefaults {
  return {
    reasoningEffort: "xhigh",
    webSearch: true,
    xSearch: true,
  };
}

export function withCreativeChatDefaults<T extends object>(value: T): T & CreativeChatDefaults {
  return { ...value, ...createCreativeChatDefaults() };
}
```

- [ ] **Step 2: Remove the promotion and import the defaults helpers**

Add this import beside the existing Creative Console imports:

```ts
import { createCreativeChatDefaults, withCreativeChatDefaults } from "@/features/creative-console/creative-console-defaults";
```

Delete only the `<aside>` block whose link points to `https://github.com/DEEIX-AI/DEEIX-Chat`. Keep `ExternalLink` imported because image, video, and voice controls still use it.

- [ ] **Step 3: Apply defaults to clear and history selection**

After `setPromptCacheKey(blank.promptCacheKey);` in `clearConversation`, add:

```ts
    setReasoningEffort(blank.reasoningEffort);
    setWebSearch(blank.webSearch);
    setXSearch(blank.xSearch);
```

In `switchConversation`, replace the three setters sourced from `target` with:

```ts
    const defaults = createCreativeChatDefaults();
    setReasoningEffort(defaults.reasoningEffort);
    setWebSearch(defaults.webSearch);
    setXSearch(defaults.xSearch);
```

Keep the existing New Conversation setters sourced from `blank`.

- [ ] **Step 4: Normalize new and restored sessions without changing messages**

Change `createBlankChatSession` to return:

```ts
  return withCreativeChatDefaults({
    id: createCreativeMessageId(),
    title: "",
    createdAt: now,
    updatedAt: now,
    model,
    promptCacheKey: createCreativeCacheKey(),
    messages: [],
  });
```

Change the `parseChatSession` return value to:

```ts
  return [withCreativeChatDefaults({
    id: value.id,
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : createChatSessionTitle(messages),
    createdAt,
    updatedAt,
    model: typeof value.model === "string" ? value.model : "",
    promptCacheKey: typeof value.promptCacheKey === "string" && value.promptCacheKey ? value.promptCacheKey : createCreativeCacheKey(),
    messages,
  })];
```

Delete `isReasoningEffort` after its final caller is removed. Do not alter `parseConversationMessage`, the storage prefix, or the fixed-reasoning model check.

- [ ] **Step 5: Run lightweight source verification**

Run:

```bash
node scripts/test-creative-console-customizations.mjs
git diff --check
```

Expected: `Creative Console customization source tests passed`; `git diff --check` prints nothing. The TypeScript test runs later on the GitHub Node 22 runner.

- [ ] **Step 6: Commit the frontend behavior**

```bash
git add frontend/src/features/creative-console/creative-console-defaults.ts frontend/src/features/creative-console/creative-console-defaults.test.ts frontend/src/features/creative-console/creative-console-page.tsx scripts/test-creative-console-customizations.mjs
git commit -m "feat: preserve production Creative Console defaults"
```

### Task 3: Restore And Verify The System Instruction Proxy

**Files:**
- Create: `scripts/system_instruction_proxy.py`
- Create: `scripts/test_system_instruction_proxy.py`
- Create: `deploy/grok-system-instruction-proxy.service`
- Create: `deploy/grok-system-instruction.caddy`
- Create: `scripts/verify-production-system-instruction.sh`

- [ ] **Step 1: Restore only the historical proxy tests and prove the implementation is absent**

```bash
git restore --source=055d7527 -- scripts/test_system_instruction_proxy.py
python3 -m unittest scripts/test_system_instruction_proxy.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.system_instruction_proxy'`.

- [ ] **Step 2: Restore the reviewed implementation from its immutable commit**

```bash
git restore --source=055d7527 -- scripts/system_instruction_proxy.py
python3 -m unittest scripts/test_system_instruction_proxy.py
python3 -m py_compile scripts/system_instruction_proxy.py
```

Expected: all tests report `OK`; bytecode compilation exits zero. These tests cover Chat Completions, Responses, Messages, authorization forwarding, invalid payloads, content lengths, and chunked SSE relay.

- [ ] **Step 3: Restore the fixed deployment assets**

```bash
git restore --source=b7a8b179 -- deploy/grok-system-instruction-proxy.service deploy/grok-system-instruction.caddy scripts/verify-production-system-instruction.sh
bash -n scripts/verify-production-system-instruction.sh
```

Expected: shell syntax check exits zero. Do not read or edit `/root/grok.md`.

- [ ] **Step 4: Commit the proxy assets**

```bash
git add scripts/system_instruction_proxy.py scripts/test_system_instruction_proxy.py deploy/grok-system-instruction-proxy.service deploy/grok-system-instruction.caddy scripts/verify-production-system-instruction.sh
git commit -m "feat: retain fixed system instruction proxy"
```

### Task 4: Replace The Frontend Overlay With Reproducible Deployment Checks

**Files:**
- Modify: `.gitignore`
- Create: `docker-compose.production.yml`
- Create: `scripts/verify-production-custom-release.sh`

- [ ] **Step 1: Ignore local worktree storage**

Add this line under the editor/temporary entries in `.gitignore`:

```gitignore
/.worktrees/
```

- [ ] **Step 2: Add the minimal production Compose override**

Create `docker-compose.production.yml` with:

```yaml
services:
  grok2api:
    container_name: grok2api-v3
```

There must be no mount whose destination is `/app/frontend/dist`; the custom image owns the complete frontend.

- [ ] **Step 3: Add a post-cutover verification script**

Create `scripts/verify-production-custom-release.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

container="${GROK2API_CONTAINER:-grok2api-v3}"
base_url="${GROK2API_BASE_URL:-https://grok2api.xiaotianyo.com}"
config_file="${GROK2API_CONFIG:-/root/grok2api-v3/config.yaml}"
db_file="${GROK2API_DB:-/var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db}"
image_ref_file="${GROK2API_IMAGE_REF_FILE:-/root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref}"
account_count_file="${GROK2API_ACCOUNT_COUNT_FILE:-/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/account-count}"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

[[ -s "$image_ref_file" ]] || fail "immutable image reference is missing"
[[ -s "$account_count_file" ]] || fail "pre-upgrade account count is missing"
expected_image="$(tr -d '\r\n' < "$image_ref_file")"
expected_accounts="$(tr -d '\r\n' < "$account_count_file")"

[[ "$(docker inspect --format '{{.State.Status}}' "$container")" == "running" ]] || fail "container is not running"
[[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == "healthy" ]] || fail "container is not healthy"
[[ "$(docker inspect --format '{{.Config.Image}}' "$container")" == "$expected_image" ]] || fail "container image is not the pinned custom image"
[[ "$(docker exec "$container" cat /app/VERSION | tr -d '\r\n')" == "v3.1.5" ]] || fail "container VERSION is not v3.1.5"

mount_destinations="$(docker inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$container")"
if grep -q '^/app/frontend' <<< "$mount_destinations"; then
  fail "legacy frontend bind mount is still active"
fi

docker exec "$container" sh -c "! grep -R -F -q 'https://github.com/DEEIX-AI/DEEIX-Chat' /app/frontend/dist" \
  || fail "compiled frontend still contains the DEEIX promotion link"
docker exec "$container" sh -c "! grep -R -F -q 'index-entry-refresh-v3-20260814' /app/frontend/dist" \
  || fail "legacy entry bootstrap is still present"

grep -Eq '^[[:space:]]+publicApiBaseURL:[[:space:]]+"https://grok2api\.xiaotianyo\.com"' "$config_file" \
  || fail "public API URL is not preserved"
[[ "$(sqlite3 "$db_file" 'PRAGMA integrity_check;')" == "ok" ]] || fail "production database integrity check failed"
[[ "$(sqlite3 "$db_file" 'SELECT COUNT(*) FROM provider_accounts;')" == "$expected_accounts" ]] \
  || fail "account count changed during upgrade"

curl --silent --show-error --fail http://127.0.0.1:8000/healthz >/dev/null || fail "local health failed"
curl --silent --show-error --fail "$base_url/" >/dev/null || fail "public root failed"
curl --silent --show-error --fail "$base_url/health" >/dev/null || fail "public health failed"

caddy validate --config /etc/caddy/Caddyfile >/dev/null || fail "Caddy validation failed"
systemctl is-active --quiet caddy grok-search grok-system-instruction-proxy || fail "required systemd service is inactive"
[[ "$(docker inspect --format '{{.State.Running}}' subboost-app-1)" == "true" ]] || fail "SubBoost app is not running"
[[ "$(docker inspect --format '{{.State.Health.Status}}' subboost-db-1)" == "healthy" ]] || fail "SubBoost database is not healthy"

"$(dirname "$0")/verify-production-system-instruction.sh"
printf 'production custom release verification passed\n'
```

- [ ] **Step 4: Validate deployment files without pulling or building**

```bash
chmod +x scripts/verify-production-custom-release.sh scripts/verify-production-system-instruction.sh
bash -n scripts/verify-production-custom-release.sh
GROK2API_CONFIG=/root/grok2api-v3/config.yaml docker compose -p grok2api-v3 -f docker-compose.yml -f docker-compose.production.yml --env-file /root/grok2api-v3/.env.production config -q
git diff --check
```

Expected: all commands exit zero and produce no Compose services with frontend bind mounts.

- [ ] **Step 5: Commit deployment metadata**

```bash
git add .gitignore docker-compose.production.yml scripts/verify-production-custom-release.sh
git commit -m "ops: prepare v3.1.5 custom image deployment"
```

### Task 5: Extend GitHub Actions For The Custom Release

**Files:**
- Modify: `.github/workflows/ghcr-image.yml:4-13`
- Modify: `.github/workflows/ghcr-image.yml:20-58`

- [ ] **Step 1: Make the production branch an explicit push target**

Change the branch trigger to:

```yaml
  push:
    branches:
      - main
      - production-v3.1.5-aurora.1
    tags:
      - "v*.*.*"
```

This leaves the Aurora fork's `main` branch untouched while allowing a fully verified branch image before the release tag is created.

- [ ] **Step 2: Add proxy and frontend tests to the existing verify job**

After checkout, add:

```yaml
      - name: Test system instruction proxy
        run: python3 -m unittest scripts/test_system_instruction_proxy.py
```

After `pnpm install`, add:

```yaml
      - name: Test frontend
        working-directory: frontend
        run: pnpm test

      - name: Verify Creative Console customizations
        run: node scripts/test-creative-console-customizations.mjs
```

Keep upstream Go tests, vet, Swagger verification, frontend lint/build, per-architecture image builds, SBOM, provenance, and manifest assembly unchanged.

- [ ] **Step 3: Run lightweight local checks and commit**

```bash
node scripts/test-creative-console-customizations.mjs
python3 -m unittest scripts/test_system_instruction_proxy.py
git diff --check
git add .github/workflows/ghcr-image.yml
git commit -m "ci: publish verified Aurora production images"
```

Expected: local tests pass. Do not run `pnpm install`, `pnpm build`, `go test ./...`, or `docker build` on this host.

### Task 6: Publish And Pin The Custom Image

**Files:**
- Read: `.github/workflows/ghcr-image.yml`
- Generate outside Git: `/root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref`

- [ ] **Step 1: Verify the branch contains only the intended base and custom commits**

```bash
git status --short --branch
git merge-base --is-ancestor v3.1.5 HEAD
git log --oneline --decorate v3.1.5..HEAD
git diff --check v3.1.5..HEAD
```

Expected: clean worktree; ancestry succeeds; the log contains the design, frontend, proxy, deployment, and CI commits only. It must not contain `3548a1e5`, `41dd68cd`, `adcc52d9`, or `183ad4fb`.

- [ ] **Step 2: Push the production branch and wait for its GitHub-hosted verification**

```bash
git push -u aurora production-v3.1.5-aurora.1
run_id="$(gh run list --repo Aurora-NEW/grok2api --workflow 'GHCR Image' --branch production-v3.1.5-aurora.1 --limit 1 --json databaseId --jq '.[0].databaseId')"
test -n "$run_id"
gh run watch "$run_id" --repo Aurora-NEW/grok2api --exit-status
```

If `gh` is unavailable, read the same public Actions run through the GitHub API. Do not proceed unless `verify`, both architecture builds, and manifest merge succeed.

- [ ] **Step 3: Create and push the immutable custom release tag**

```bash
git tag -a v3.1.5-aurora.2 -m "Grok2API v3.1.5 Aurora production release 2"
git push aurora v3.1.5-aurora.2
sleep 5
run_id="$(gh run list --repo Aurora-NEW/grok2api --workflow 'GHCR Image' --commit "$(git rev-parse HEAD)" --event push --limit 1 --json databaseId --jq '.[0].databaseId')"
test -n "$run_id"
gh run watch "$run_id" --repo Aurora-NEW/grok2api --exit-status
```

Wait for the tag's `GHCR Image` workflow and require every job to pass. If it fails, do not move or reuse the tag; fix the branch and use `v3.1.5-aurora.3` in a revised plan.

- [ ] **Step 4: Resolve and record the immutable manifest digest**

```bash
image="ghcr.io/aurora-new/grok2api:v3.1.5-aurora.2"
digest="$(docker buildx imagetools inspect "$image" | awk '/^Digest:/ {print $2; exit}')"
test "${digest#sha256:}" != "$digest"
install -d -m 700 /root/backups/grok2api-v3
printf '%s@%s\n' "$image" "$digest" | tee /root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref
chmod 600 /root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref
```

Expected: the file contains one tag-plus-`sha256` manifest reference and `test` confirms the digest prefix. If GHCR denies anonymous inspection, stop and make the package public or configure read-only GHCR authentication; never place a token in Git.

### Task 7: Back Up Production And Run A Resource-Limited Canary

**Files:**
- Read: `/root/AGENTS.md`
- Back up: `/var/lib/docker/volumes/grok2api-v3_grok2api-data/_data`
- Back up: `/root/grok2api-v3/config.yaml`, `/root/grok2api-v3/.env.production`, Compose files, Caddy, and frontend overlays
- Generate: `/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/`

- [ ] **Step 1: Run the mandatory host and service preflight**

```bash
nproc
uptime
free -h
swapon --show
df -h / /var/lib/docker
docker stats --no-stream
docker inspect --format '{{.State.Status}} {{.State.Health.Status}} {{.Image}}' grok2api-v3
systemctl is-active caddy grok-search grok-system-instruction-proxy
caddy validate --config /etc/caddy/Caddyfile
```

Expected: 2 CPUs, production healthy, required services active, adequate disk, and enough available RAM plus swap for one container limited below. Do not run any build or second heavy job.

- [ ] **Step 2: Create and validate an online SQLite backup**

```bash
test ! -e /root/backups/grok2api-v3/pre-v3.1.5-aurora.2
install -d -m 700 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2
sqlite3 /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db ".backup '/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/backend.db'"
chmod 600 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/backend.db
sqlite3 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/backend.db 'PRAGMA integrity_check;'
sqlite3 /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db 'SELECT COUNT(*) FROM provider_accounts;' | tee /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/account-count
```

Expected: integrity check prints `ok`; account count is a positive integer.

- [ ] **Step 3: Back up deployment configuration and construct cloned canary data**

```bash
cp -a /root/grok2api-v3/config.yaml /root/grok2api-v3/.env.production /root/grok2api-v3/docker-compose.yml /root/grok2api-v3/docker-compose.production.yml /etc/caddy/Caddyfile /etc/systemd/system/grok-system-instruction-proxy.service /usr/local/libexec/grok-system-instruction-proxy.py /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/
cp -a /root/grok2api-v3/index.production.html /root/grok2api-v3/frontend.production /root/grok2api-v3/frontend/public/creative-console-chat-defaults-v1.js /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/
docker inspect grok2api-v3 > /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/grok2api-v3.inspect.json
install -d -m 700 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/canary-quality
cp -a /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/. /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data/
install -o 10001 -g 10001 -m 600 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/backend.db /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data/backend.db
rm -f /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data/backend.db-wal /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data/backend.db-shm
```

Expected: production continues running; only the clone is modified.

- [ ] **Step 4: Pull the prebuilt image and start one limited canary**

```bash
image_ref="$(tr -d '\r\n' < /root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref)"
docker pull "$image_ref"
docker run -d --name grok2api-v315-canary --memory=192m --memory-swap=384m --cpus=0.5 --pids-limit=128 --init -p 127.0.0.1:18000:8000 -e TZ=Asia/Shanghai -v /root/grok2api-v3/config.yaml:/run/grok2api/config.yaml:ro -v /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data:/app/data -v /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/canary-quality:/var/lib/grok2api-quality-guard "$image_ref"
for attempt in $(seq 1 60); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' grok2api-v315-canary)"
  [[ "$health" == "healthy" ]] && break
  [[ "$health" == "unhealthy" ]] && exit 1
  if (( attempt % 5 == 0 )); then
    docker stats --no-stream grok2api-v315-canary
    free -h
  fi
  sleep 2
done
test "$(docker inspect --format '{{.State.Health.Status}}' grok2api-v315-canary)" = "healthy"
```

Expected: the canary becomes healthy within 120 seconds. Stop immediately if the periodic resource output shows sustained swap growth or the host loses responsiveness.

- [ ] **Step 5: Validate migrated clone, image contents, and production coexistence**

```bash
curl --silent --show-error --fail http://127.0.0.1:18000/healthz
docker exec grok2api-v315-canary cat /app/VERSION
docker exec grok2api-v315-canary sh -c "! grep -R -F -q 'https://github.com/DEEIX-AI/DEEIX-Chat' /app/frontend/dist"
test "$(sqlite3 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data/backend.db 'SELECT COUNT(*) FROM provider_accounts;')" = "$(cat /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/account-count)"
docker logs --since 5m grok2api-v315-canary
docker inspect --format '{{.State.Health.Status}}' grok2api-v3
```

Expected: canary and production are healthy, version is `v3.1.5`, promotion link is absent, account count matches, and logs contain no migration error or panic.

- [ ] **Step 6: Remove the canary and revalidate its database**

```bash
docker rm -f grok2api-v315-canary
sqlite3 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/staging-data/backend.db 'PRAGMA integrity_check;'
docker inspect --format '{{.State.Health.Status}}' grok2api-v3
```

Expected: integrity prints `ok`; production remains healthy. Do not proceed if either check fails.

### Task 8: Cut Over The Production Container

**Files:**
- Modify: `/root/grok2api-v3/.env.production`
- Modify: `/etc/caddy/Caddyfile:33-38`
- Switch checkout: `/root/grok2api-v3` to `production-v3.1.5-aurora.1`

- [ ] **Step 1: Make the clean custom branch the production checkout**

From `/root`, verify both worktrees are clean and the release tag points at the branch tip. Remove only `/root/grok2api-v3/.worktrees/v3-1-5-aurora`, then switch the main checkout:

```bash
git -C /root/grok2api-v3/.worktrees/v3-1-5-aurora status --short
git -C /root/grok2api-v3 status --short
git -C /root/grok2api-v3 rev-parse production-v3.1.5-aurora.1
git -C /root/grok2api-v3 rev-parse v3.1.5-aurora.2
test "$(git -C /root/grok2api-v3 rev-parse production-v3.1.5-aurora.1)" = "$(git -C /root/grok2api-v3 rev-parse v3.1.5-aurora.2)"
git -C /root/grok2api-v3 worktree remove /root/grok2api-v3/.worktrees/v3-1-5-aurora
git -C /root/grok2api-v3 switch production-v3.1.5-aurora.1
```

Expected: the two revisions match. Leave the separate `feature/console-capacity-failover` worktree untouched and unmerged.

- [ ] **Step 2: Pin the recorded image and replace the obsolete Caddy cache rule**

Use `apply_patch` to replace the value after `GROK2API_IMAGE=` in `/root/grok2api-v3/.env.production` with the exact image reference stored in `/root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref`. Preserve the `GROK2API_IMAGE=` key.

Use `apply_patch` on `/etc/caddy/Caddyfile` to replace:

```caddyfile
	# This entry is imported by every lazy chunk and must retain its canonical
	# URL. Revalidate it so frontend hotfixes cannot be pinned for a year.
	@canonical_frontend_entry path /assets/index-DVIk9Mqh.js
	header @canonical_frontend_entry Cache-Control "no-cache"
```

with:

```caddyfile
	# Revalidate the HTML shell; immutable hashed assets remain cacheable.
	@frontend_html path / /index.html
	header @frontend_html Cache-Control "no-cache"
```

Do not alter the authorization map, instruction-proxy routes, `flush_interval -1`, MCP site, or SubBoost site.

- [ ] **Step 3: Validate the exact merged deployment before recreation**

```bash
cd /root/grok2api-v3
docker compose -p grok2api-v3 -f docker-compose.yml -f docker-compose.production.yml --env-file .env.production config -q
caddy validate --config /etc/caddy/Caddyfile
docker inspect --format '{{.State.Health.Status}} {{.Config.Image}}' grok2api-v3
```

Expected: Compose and Caddy validate; old production is still healthy. Inspect the merged Compose output and confirm the named volumes remain `grok2api-v3_grok2api-data` and `grok2api-v3_quality_guard_state`, with no `/app/frontend` mounts.

- [ ] **Step 4: Recreate only Grok2API from the pinned prebuilt image**

```bash
docker compose -p grok2api-v3 -f docker-compose.yml -f docker-compose.production.yml --env-file .env.production up -d --no-deps --force-recreate grok2api
for attempt in $(seq 1 60); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' grok2api-v3)"
  [[ "$health" == "healthy" ]] && break
  [[ "$health" == "unhealthy" ]] && exit 1
  if (( attempt % 5 == 0 )); then
    docker stats --no-stream grok2api-v3
    docker logs --since 1m grok2api-v3
  fi
  sleep 2
done
test "$(docker inspect --format '{{.State.Health.Status}}' grok2api-v3)" = "healthy"
```

Expected: the container becomes healthy within 120 seconds. If the command exits nonzero, do not reload Caddy; execute Task 10 immediately.

- [ ] **Step 5: Reload Caddy only after backend health succeeds**

```bash
systemctl reload caddy
systemctl is-active caddy grok-search grok-system-instruction-proxy
curl --silent --show-error --fail https://grok2api.xiaotianyo.com/health
```

Expected: all services active and public health succeeds.

### Task 9: Verify Data, Defaults, Streaming, And Companion Services

**Files:**
- Run: `scripts/verify-production-custom-release.sh`
- Generate: `/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/stream-smoke.log`

- [ ] **Step 1: Run the complete production verification script**

```bash
cd /root/grok2api-v3
./scripts/verify-production-custom-release.sh
```

Expected: `production custom release verification passed`. This verifies the pinned image, absence of frontend mounts and promotion link, database integrity/account count, public URL, Caddy, system instruction routes, active and legacy client keys, GrokSearch, and SubBoost.

- [ ] **Step 2: Run one real streaming Responses smoke test with both search tools**

Read the active client key without printing it, prefer `grok-chat-fast`, and otherwise choose the first model whose name is not a media/voice model:

```bash
set -o pipefail
umask 077
active_key="$(tr -d '\r\n' < /root/grok2api-v3/.client-key)"
models_json="$(curl --silent --show-error --fail -H "Authorization: Bearer $active_key" https://grok2api.xiaotianyo.com/v1/models)"
model="$(jq -r '([.data[].id | select(. == "grok-chat-fast")][0] // [.data[].id | select(test("imagine|voice|stt|tts"; "i") | not)][0] // empty)' <<< "$models_json")"
test -n "$model"
payload="$(jq -nc --arg model "$model" '{model:$model,input:[{role:"user",content:"Use web search and X search, then answer with one short sentence."}],stream:true,store:false,reasoning:{effort:"xhigh",summary:"auto"},tools:[{type:"web_search"},{type:"x_search"}]}')"
stream_log=/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/stream-smoke.log
header_log=/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/stream-smoke.headers
curl --no-buffer --silent --show-error --fail-with-body --max-time 240 -D "$header_log" -H "Authorization: Bearer $active_key" -H 'Content-Type: application/json' --data-binary "$payload" https://grok2api.xiaotianyo.com/v1/responses | awk '{ print strftime("%Y-%m-%dT%H:%M:%S%z"), $0; fflush(); }' > "$stream_log"
chmod 600 "$stream_log" "$header_log"
rg -q 'response\.(completed|incomplete)' "$stream_log"
! rg -qi 'Contract check:' "$stream_log"
tool_line="$(rg -n -m1 'response\.output_item\.added.*(web_search_call|x_search_call)' "$stream_log" | cut -d: -f1)"
text_line="$(rg -n -m1 'response\.output_text\.delta' "$stream_log" | cut -d: -f1)"
test -n "$tool_line"
test -n "$text_line"
test "$tool_line" -lt "$text_line"
```

Expected: the stream terminates successfully, contains no stray contract-check text, and exposes a search activity event before answer text. Treat an upstream capacity error as an upstream smoke-test failure, not permission to modify account scheduling in this release.

- [ ] **Step 3: Confirm browser-local history and lifecycle behavior**

Using the existing HTTPS origin and existing browser profile:

1. Open Creative Console and confirm an old conversation still contains its messages.
2. Confirm Web Search and X Search are on and reasoning is `xhigh`.
3. Click New Conversation and confirm all three remain at their defaults.
4. Switch to an old history item and confirm messages remain while the three controls return to defaults.
5. Confirm no DEEIX Chat promotion is rendered.

Do not clear cookies, local storage, or site data. The fixed Console reasoning model may show `auto` as designed.

- [ ] **Step 4: Observe the host and service logs before declaring success**

```bash
docker stats --no-stream
free -h
swapon --show
docker logs --since 10m grok2api-v3
journalctl -u grok-system-instruction-proxy --since '10 minutes ago' --no-pager
systemctl is-active caddy grok-search grok-system-instruction-proxy
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

Expected: no restart loop, panic, migration error, sustained memory pressure, or inactive companion service. Keep the old image, backup, and swap unchanged during the observation window.

### Task 10: Roll Back Atomically If A Critical Gate Fails

**Files:**
- Restore: `/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/backend.db`
- Restore: saved `.env.production` and `Caddyfile`
- Switch: `production-migration-20260814`

- [ ] **Step 1: Stop the new backend without removing volumes**

```bash
cd /root/grok2api-v3
docker compose -p grok2api-v3 -f docker-compose.yml -f docker-compose.production.yml --env-file .env.production stop grok2api
```

- [ ] **Step 2: Restore the matching pre-upgrade SQLite database**

```bash
rm -f /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db-wal /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db-shm
install -o 10001 -g 10001 -m 600 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/backend.db /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db
sqlite3 /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db 'PRAGMA integrity_check;'
```

Expected: `ok`. This intentionally discards Grok2API writes made after cutover; SubBoost data is untouched.

- [ ] **Step 3: Restore the old checkout and deployment configuration**

```bash
git -C /root/grok2api-v3 switch production-migration-20260814
install -m 600 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/.env.production /root/grok2api-v3/.env.production
install -m 644 /root/backups/grok2api-v3/pre-v3.1.5-aurora.2/Caddyfile /etc/caddy/Caddyfile
cd /root/grok2api-v3
docker compose -p grok2api-v3 -f docker-compose.yml -f docker-compose.production.yml --env-file .env.production up -d --no-deps --force-recreate grok2api
```

- [ ] **Step 4: Restore routing and verify the old snapshot**

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
docker inspect --format '{{.State.Health.Status}} {{.Config.Image}}' grok2api-v3
./scripts/verify-production-system-instruction.sh
```

Expected: old digest `sha256:5bc81cebbf941a44009927ba880b9a25d983aaeb41f6833ee7dc57195203c0e7` is healthy and instruction routing works. Preserve the failed custom image and logs for diagnosis; do not retry production in the same window.

### Task 11: Record The Successful Release

**Files:**
- Read: Git and Docker metadata
- Preserve: rollback backup and old image

- [ ] **Step 1: Record the deployed state**

Write the non-secret deployment record, then use it as the source for the user-facing summary:

```bash
record=/root/backups/grok2api-v3/pre-v3.1.5-aurora.2/deployed-state.txt
{
  git -C /root/grok2api-v3 rev-parse HEAD
  git -C /root/grok2api-v3 describe --tags --exact-match HEAD
  tr -d '\r\n' < /root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref
  printf '\n'
  docker image inspect --format '{{.Id}}' "$(tr -d '\r\n' < /root/backups/grok2api-v3/v3.1.5-aurora.2-image-ref)"
  docker inspect --format '{{.Image}} {{.State.Health.Status}}' grok2api-v3
  sqlite3 /var/lib/docker/volumes/grok2api-v3_grok2api-data/_data/backend.db 'PRAGMA integrity_check; SELECT COUNT(*) FROM provider_accounts;'
  systemctl is-active caddy grok-search grok-system-instruction-proxy
} > "$record"
chmod 600 "$record"
```

Do not add credentials, `/root/grok.md` contents, authorization maps, or request bodies to this record.

- [ ] **Step 2: Confirm repository and production health one final time**

```bash
git -C /root/grok2api-v3 status --short --branch
git -C /root/grok2api-v3 log -1 --oneline --decorate
docker inspect --format '{{.State.Health.Status}} {{.Config.Image}}' grok2api-v3
systemctl is-active caddy grok-search grok-system-instruction-proxy
```

Expected: clean `production-v3.1.5-aurora.1` checkout, custom release tag at its tip, healthy pinned container, and active companion services. Do not delete the old production branch, old image, database backup, frontend overlay backup, or the isolated capacity-failover worktree.
