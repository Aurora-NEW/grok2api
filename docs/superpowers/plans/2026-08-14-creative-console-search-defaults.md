# Creative Console Search Defaults Implementation Plan

> **V2 amendment:** The user does not need chat-setting choices to persist across reloads. The deployed v2 must normalize restored sessions and history switches to `xhigh/on/on`; the fixed Console reasoning model remains `auto` because its upstream contract rejects configurable effort.

> **V3 amendment:** A renamed main entry creates a second ES module instance because existing lazy chunks import `/assets/index-DVIk9Mqh.js`. Deploy the corrected main bytes at that canonical URL, use a versioned bootstrap for one forced cache refresh, and serve the canonical entry with `Cache-Control: no-cache`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make restored, selected, cleared, and new Creative Console chat sessions start with Web Search and X Search enabled and `xhigh` reasoning; manual changes only last in the current page state.

**Architecture:** Runtime session parsing and history selection normalize search and reasoning state instead of restoring saved values. A compatibility migration remains for v1 pages. Production pins a versioned Creative Console chunk but preserves the main bundle's canonical module URL, with a versioned cache-refresh bootstrap, because this host cannot safely compile the frontend.

**Tech Stack:** TypeScript/React, browser `localStorage`, plain JavaScript, Node built-in test modules, Docker Compose, Caddy

---

## File Map

- Create `frontend/public/creative-console-chat-defaults-v1.js`: one-time per-scope browser migration.
- Create `scripts/test-creative-console-chat-defaults.mjs`: dependency-free migration and source behavior tests.
- Modify `frontend/index.html`: run the migration before the application module in future builds/dev.
- Modify `frontend/src/features/creative-console/creative-console-page.tsx`: future blank and clear defaults.
- Create `frontend.production/index-search-defaults-v1-20260814.js`: pinned current main bundle with a new lazy-chunk reference.
- Create `frontend.production/creative-console-search-defaults-v1-20260814.js`: pinned current Creative Console bundle with equivalent runtime changes.
- Modify `index.production.html`: load migration then the newly versioned main bundle.
- Modify `docker-compose.production.yml`: mount the migration and both pinned bundles read-only.
- Create `scripts/verify-production-chat-defaults.sh`: static, container, and public deployment verification.
- Create `frontend.production/index-DVIk9Mqh.js`: corrected main bundle at the canonical module URL shared by lazy chunks.
- Create `frontend.production/index-entry-refresh-v3-20260814.js`: one-time browser cache refresh followed by canonical import.
- Modify `/etc/caddy/Caddyfile`: revalidate the canonical main bundle instead of serving it as immutable.

### Task 1: One-Time Browser Migration

**Files:**
- Create: `scripts/test-creative-console-chat-defaults.mjs`
- Create: `frontend/public/creative-console-chat-defaults-v1.js`
- Modify: `frontend/index.html`

- [ ] **Step 1: Write the failing Node test**

Create `scripts/test-creative-console-chat-defaults.mjs` with:

```js
#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const migrationPath = path.join(repoRoot, "frontend/public/creative-console-chat-defaults-v1.js");
const sourcePath = path.join(repoRoot, "frontend/src/features/creative-console/creative-console-page.tsx");
const migrationSource = fs.readFileSync(migrationPath, "utf8");
const historyPrefix = "grok2api:creative-console:chat-history:";
const markerPrefix = "grok2api:creative-console:chat-defaults-v1:";

class FakeStorage {
  constructor(entries = {}) { this.entries = new Map(Object.entries(entries)); }
  get length() { return this.entries.size; }
  key(index) { return [...this.entries.keys()][index] ?? null; }
  getItem(key) { return this.entries.has(key) ? this.entries.get(key) : null; }
  setItem(key, value) { this.entries.set(String(key), String(value)); }
  removeItem(key) { this.entries.delete(key); }
}

function runMigration(storage) {
  vm.runInNewContext(migrationSource, { window: { localStorage: storage } });
}

const scope = "client%20key";
const malformedScope = "broken";
const historyKey = `${historyPrefix}${scope}`;
const malformedKey = `${historyPrefix}${malformedScope}`;
const originalSession = {
  id: "session-1",
  reasoningEffort: "auto",
  webSearch: false,
  xSearch: false,
  messages: [{ role: "user", content: "hello" }],
};
const storage = new FakeStorage({
  [historyKey]: JSON.stringify([originalSession]),
  [malformedKey]: "not-json",
});

runMigration(storage);
const [migratedSession] = JSON.parse(storage.getItem(historyKey));
assert.deepEqual(migratedSession, {
  ...originalSession,
  reasoningEffort: "xhigh",
  webSearch: true,
  xSearch: true,
});
assert.equal(storage.getItem(`${markerPrefix}${scope}`), "1");
assert.equal(storage.getItem(malformedKey), "not-json");
assert.equal(storage.getItem(`${markerPrefix}${malformedScope}`), null);

storage.setItem(historyKey, JSON.stringify([{
  ...migratedSession,
  reasoningEffort: "auto",
  webSearch: false,
  xSearch: false,
}]));
runMigration(storage);
const [afterSecondRun] = JSON.parse(storage.getItem(historyKey));
assert.equal(afterSecondRun.reasoningEffort, "auto");
assert.equal(afterSecondRun.webSearch, false);
assert.equal(afterSecondRun.xSearch, false);

const throwingWindow = {};
Object.defineProperty(throwingWindow, "localStorage", { get() { throw new Error("blocked"); } });
assert.doesNotThrow(() => vm.runInNewContext(migrationSource, { window: throwingWindow }));

if (process.argv.includes("--migration-only")) {
  console.log("creative console chat defaults migration tests passed");
  process.exit(0);
}

const source = fs.readFileSync(sourcePath, "utf8");
const blankStart = source.indexOf("function createBlankChatSession");
const blankEnd = source.indexOf("function createChatSessionTitle", blankStart);
const blankBlock = source.slice(blankStart, blankEnd);
assert.match(blankBlock, /reasoningEffort: "xhigh",/);
assert.match(blankBlock, /webSearch: true,/);
assert.match(blankBlock, /xSearch: true,/);

const clearStart = source.indexOf("function clearConversation");
const clearEnd = source.indexOf("function startNewConversation", clearStart);
const clearBlock = source.slice(clearStart, clearEnd);
assert.match(clearBlock, /setReasoningEffort\(blank\.reasoningEffort\);/);
assert.match(clearBlock, /setWebSearch\(blank\.webSearch\);/);
assert.match(clearBlock, /setXSearch\(blank\.xSearch\);/);

console.log("creative console chat defaults tests passed");
```

- [ ] **Step 2: Run the test and observe RED**

Run:

```bash
node scripts/test-creative-console-chat-defaults.mjs
```

Expected: non-zero exit because `frontend/public/creative-console-chat-defaults-v1.js` is missing and the TypeScript source still contains `auto/false/false`.

- [ ] **Step 3: Implement the migration script**

Create `frontend/public/creative-console-chat-defaults-v1.js` with:

```js
(() => {
  const historyPrefix = "grok2api:creative-console:chat-history:";
  const markerPrefix = "grok2api:creative-console:chat-defaults-v1:";

  try {
    const storage = window.localStorage;
    const historyKeys = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(historyPrefix)) historyKeys.push(key);
    }

    for (const historyKey of historyKeys) {
      const scope = historyKey.slice(historyPrefix.length);
      const markerKey = `${markerPrefix}${scope}`;
      if (storage.getItem(markerKey) === "1") continue;

      try {
        const sessions = JSON.parse(storage.getItem(historyKey) ?? "[]");
        if (!Array.isArray(sessions)) continue;
        const migrated = sessions.map((session) => (
          session && typeof session === "object" && !Array.isArray(session)
            ? { ...session, reasoningEffort: "xhigh", webSearch: true, xSearch: true }
            : session
        ));
        storage.setItem(historyKey, JSON.stringify(migrated));
        storage.setItem(markerKey, "1");
      } catch {
        // A broken history entry must not prevent the application from loading.
      }
    }
  } catch {
    // Browser storage may be disabled or unavailable.
  }
})();
```

Add this before `/runtime-config.js` in `frontend/index.html`:

```html
<script src="/creative-console-chat-defaults-v1.js"></script>
```

- [ ] **Step 4: Run the migration-only assertions**

Run:

```bash
node scripts/test-creative-console-chat-defaults.mjs --migration-only
```

Expected: `creative console chat defaults migration tests passed`.

- [ ] **Step 5: Commit the migration unit**

```bash
git add frontend/public/creative-console-chat-defaults-v1.js frontend/index.html scripts/test-creative-console-chat-defaults.mjs
git commit -m "feat: migrate saved chat defaults once"
```

### Task 2: Source Defaults and Reset Paths

**Files:**
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx:595-640`
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx:1780-1793`
- Test: `scripts/test-creative-console-chat-defaults.mjs`

- [ ] **Step 1: Confirm the full test is RED**

Run:

```bash
node scripts/test-creative-console-chat-defaults.mjs
```

Expected: failure identifying the old blank defaults or missing clear-state setter calls.

- [ ] **Step 2: Change blank-session defaults**

Update `createBlankChatSession()` to:

```ts
reasoningEffort: "xhigh",
webSearch: true,
xSearch: true,
```

- [ ] **Step 3: Reset settings when clearing a conversation**

Immediately after `setPromptCacheKey(blank.promptCacheKey);` in `clearConversation()`, add:

```ts
setReasoningEffort(blank.reasoningEffort);
setWebSearch(blank.webSearch);
setXSearch(blank.xSearch);
```

`startNewConversation()` already performs these assignments and remains unchanged. The fixed Console reasoning model continues to coerce the effective value to `auto`.

- [ ] **Step 4: Run the full test GREEN**

Run:

```bash
node scripts/test-creative-console-chat-defaults.mjs
```

Expected: `creative console chat defaults tests passed`.

- [ ] **Step 5: Commit source behavior**

```bash
git add frontend/src/features/creative-console/creative-console-page.tsx scripts/test-creative-console-chat-defaults.mjs
git commit -m "feat: apply chat defaults to blank sessions"
```

### Task 3: Versioned Production Assets

**Files:**
- Create: `frontend.production/index-search-defaults-v1-20260814.js`
- Create: `frontend.production/creative-console-search-defaults-v1-20260814.js`
- Modify: `index.production.html`
- Modify: `docker-compose.production.yml`
- Create: `scripts/verify-production-chat-defaults.sh`

- [ ] **Step 1: Write and run the failing production verifier**

Create `scripts/verify-production-chat-defaults.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_file="$repo_root/frontend/src/features/creative-console/creative-console-page.tsx"
migration_file="$repo_root/frontend/public/creative-console-chat-defaults-v1.js"
main_asset="$repo_root/frontend.production/index-search-defaults-v1-20260814.js"
console_asset="$repo_root/frontend.production/creative-console-search-defaults-v1-20260814.js"
compose_file="$repo_root/docker-compose.production.yml"
index_file="$repo_root/index.production.html"
base_url="${GROK2API_BASE_URL:-https://grok2api.xiaotianyo.com}"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

node "$repo_root/scripts/test-creative-console-chat-defaults.mjs"
[[ -s "$migration_file" ]] || fail "migration script is missing"
[[ -s "$main_asset" ]] || fail "versioned main bundle is missing"
[[ -s "$console_asset" ]] || fail "versioned Creative Console bundle is missing"

new_defaults='reasoningEffort:`xhigh`,webSearch:!0,xSearch:!0'
clear_reset='ne(e.promptCacheKey),T(e.reasoningEffort),S(e.webSearch),w(e.xSearch),L(``)'
[[ "$(grep -oF "$new_defaults" "$console_asset" | wc -l || true)" == 1 ]] \
  || fail "production bundle does not contain one new-default block"
[[ "$(grep -oF "$clear_reset" "$console_asset" | wc -l || true)" == 2 ]] \
  || fail "production bundle does not contain both reset paths"
[[ "$(grep -oF 'creative-console-page-CN1zhJR-.js' "$main_asset" | wc -l || true)" == 0 ]] \
  || fail "main bundle still references the old Creative Console chunk"
[[ "$(grep -oF 'creative-console-search-defaults-v1-20260814.js' "$main_asset" | wc -l || true)" == 2 ]] \
  || fail "main bundle does not contain both new lazy-chunk references"

grep -Fq './frontend/public/creative-console-chat-defaults-v1.js:/app/frontend/dist/creative-console-chat-defaults-v1.js:ro' "$compose_file" \
  || fail "migration mount is missing"
grep -Fq './frontend.production/index-search-defaults-v1-20260814.js:/app/frontend/dist/assets/index-search-defaults-v1-20260814.js:ro' "$compose_file" \
  || fail "main bundle mount is missing"
grep -Fq './frontend.production/creative-console-search-defaults-v1-20260814.js:/app/frontend/dist/assets/creative-console-search-defaults-v1-20260814.js:ro' "$compose_file" \
  || fail "Creative Console bundle mount is missing"

node --check "$migration_file"
node --input-type=module --check < "$main_asset"
node --input-type=module --check < "$console_asset"
node --input-type=module - "$index_file" <<'NODE'
import fs from "node:fs";
const html = fs.readFileSync(process.argv[2], "utf8");
const migration = html.indexOf('/creative-console-chat-defaults-v1.js');
const entrypoint = html.indexOf('/assets/index-search-defaults-v1-20260814.js');
if (migration < 0 || entrypoint < 0 || migration >= entrypoint) process.exit(1);
NODE

for relative_path in \
  creative-console-chat-defaults-v1.js \
  assets/index-search-defaults-v1-20260814.js \
  assets/creative-console-search-defaults-v1-20260814.js; do
  case "$relative_path" in
    creative-console-chat-defaults-v1.js) local_file="$migration_file" ;;
    assets/index-search-defaults-v1-20260814.js) local_file="$main_asset" ;;
    *) local_file="$console_asset" ;;
  esac
  local_hash="$(sha256sum "$local_file" | awk '{print $1}')"
  container_hash="$(docker exec grok2api-v3 sha256sum "/app/frontend/dist/$relative_path" 2>/dev/null | awk '{print $1}' || true)"
  public_hash="$(curl --silent --show-error --fail "$base_url/$relative_path" | sha256sum | awk '{print $1}' || true)"
  [[ "$container_hash" == "$local_hash" ]] || fail "$relative_path container hash mismatch"
  [[ "$public_hash" == "$local_hash" ]] || fail "$relative_path public hash mismatch"
done

curl --silent --show-error --fail "$base_url/creative-console" \
  | grep -F '/assets/index-search-defaults-v1-20260814.js' >/dev/null \
  || fail "public HTML does not reference the new main bundle"

printf 'production chat defaults verification passed\n'
```

Run:

```bash
./scripts/verify-production-chat-defaults.sh
```

Expected: failure because the new versioned production assets do not exist.

- [ ] **Step 2: Extract current pinned assets**

```bash
docker cp grok2api-v3:/app/frontend/dist/assets/index-DVIk9Mqh.js frontend.production/index-search-defaults-v1-20260814.js
docker cp grok2api-v3:/app/frontend/dist/assets/creative-console-page-CN1zhJR-.js frontend.production/creative-console-search-defaults-v1-20260814.js
```

- [ ] **Step 3: Apply exact mechanical substitutions**

Assert each old pattern count before replacing it. In the Creative Console bundle replace:

```text
reasoningEffort:`auto`,webSearch:!1,xSearch:!1
```

with:

```text
reasoningEffort:`xhigh`,webSearch:!0,xSearch:!0
```

and replace the single clear path:

```text
ne(e.promptCacheKey),L(``)
```

with:

```text
ne(e.promptCacheKey),T(e.reasoningEffort),S(e.webSearch),w(e.xSearch),L(``)
```

In the main bundle replace both occurrences of:

```text
creative-console-page-CN1zhJR-.js
```

with:

```text
creative-console-search-defaults-v1-20260814.js
```

- [ ] **Step 4: Pin HTML and Compose mounts**

In `index.production.html`, place:

```html
<script src="/creative-console-chat-defaults-v1.js"></script>
<script src="/runtime-config.js"></script>
<script type="module" crossorigin src="/assets/index-search-defaults-v1-20260814.js"></script>
```

Add these read-only mounts to `docker-compose.production.yml`:

```yaml
- "./frontend/public/creative-console-chat-defaults-v1.js:/app/frontend/dist/creative-console-chat-defaults-v1.js:ro"
- "./frontend.production/index-search-defaults-v1-20260814.js:/app/frontend/dist/assets/index-search-defaults-v1-20260814.js:ro"
- "./frontend.production/creative-console-search-defaults-v1-20260814.js:/app/frontend/dist/assets/creative-console-search-defaults-v1-20260814.js:ro"
```

- [ ] **Step 5: Run static verification**

```bash
bash -n scripts/verify-production-chat-defaults.sh
docker compose -p grok2api-v3 --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml config --quiet
node --check frontend/public/creative-console-chat-defaults-v1.js
node --input-type=module --check < frontend.production/index-search-defaults-v1-20260814.js
node --input-type=module --check < frontend.production/creative-console-search-defaults-v1-20260814.js
```

Expected: syntax and Compose checks pass; the deployment verifier stops only because the running container does not yet have the new mounts.

### Task 4: Production Deployment and Verification

**Files:**
- Verify: `docker-compose.production.yml`
- Verify: `scripts/verify-production-chat-defaults.sh`
- Verify: `scripts/verify-production-system-instruction.sh`

- [ ] **Step 1: Record pre-deployment health**

Confirm Docker reports `running/healthy/0`, and `caddy`, `grok-search`, and `grok-system-instruction-proxy` are active. Do not run a build, dependency install, image pull, or full test suite.

- [ ] **Step 2: Recreate only the pinned production container**

```bash
docker compose \
  -p grok2api-v3 \
  --env-file .env.production \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  up -d --force-recreate --no-deps --pull never grok2api
```

Wait up to 60 seconds for Docker health and stop on `exited` or `dead`.

- [ ] **Step 3: Run production verification**

```bash
./scripts/verify-production-chat-defaults.sh
./scripts/verify-production-system-instruction.sh
```

Expected: both scripts pass; public HTML loads migration before the entry bootstrap; public bundle hashes match local and container copies.

- [ ] **Step 4: Check health and logs**

Require:

```text
grok2api-v3: running/healthy, restarts=0
caddy: active
grok-search: active
grok-system-instruction-proxy: active
```

Search recent container logs for `error`, `exception`, `traceback`, `fatal`, `panic`, and `oom`; investigate any matches before continuing.

- [ ] **Step 5: Commit and perform fresh final verification**

```bash
git add frontend.production index.production.html docker-compose.production.yml scripts/verify-production-chat-defaults.sh
git commit -m "ops: deploy effective chat defaults"
```

Then rerun both verification scripts, Docker and systemd health assertions, `git diff --check` excluding generated bundles, and require a clean worktree.

### Task 5: Restore Canonical ES Module Identity

**Files:**
- Create: `frontend.production/index-DVIk9Mqh.js`
- Create: `frontend.production/index-entry-refresh-v3-20260814.js`
- Modify: `index.production.html`
- Modify: `docker-compose.production.yml`
- Modify: `/etc/caddy/Caddyfile`
- Modify: `scripts/verify-production-chat-defaults.sh`

- [x] **Step 1: Reproduce the module-identity failure**

Load the public page in one constrained Playwright browser with mocked admin APIs and an old saved `auto/off/off` session. Verify the renamed v2 entry loads `/assets/index-DVIk9Mqh.js` as a second module, emits `useAuth must be used inside AuthProvider`, and displays `auto/off/off` before and after New Conversation.

- [x] **Step 2: Verify the canonical-entry hypothesis without changing production**

Intercept the HTML to load `/assets/index-DVIk9Mqh.js` and fulfill that URL with the corrected main bytes. Require Web Search enabled, X Search enabled, and `xhigh` both before and after New Conversation, with no React context error.

- [x] **Step 3: Deploy the canonical entry and cache bootstrap**

Copy the verified v2 main bytes to `frontend.production/index-DVIk9Mqh.js`. Mount it over the image's canonical entry, mount `index-entry-refresh-v3-20260814.js`, load the bootstrap from production HTML, and set the canonical entry response to `Cache-Control: no-cache` in Caddy.

- [x] **Step 4: Recreate and verify production**

Recreate only `grok2api` with `--pull never`, reload Caddy, and run:

```bash
./scripts/verify-production-chat-defaults.sh
./scripts/verify-production-system-instruction.sh
```

Expected: both pass, the locked image digest is unchanged, and all three services remain active.

- [x] **Step 5: Run the real-browser regression against production**

Use one Chromium page under `CPUQuota=100%`, `MemoryHigh=450M`, and `MemoryMax=650M`. Require the accessible labels before and after New Conversation to be `联网搜索: 开启联网搜索`, `X 搜索: 开启 X 搜索`, and `推理模式: 极高`.
