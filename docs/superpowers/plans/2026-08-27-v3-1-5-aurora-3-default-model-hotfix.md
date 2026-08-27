# v3.1.5 Aurora.3 Default Model Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user explicitly disabled subagents for this work.

**Goal:** Make a fresh Creative Console chat select `grok-4.20-multi-agent-0309` so the existing Web search, X search, and `xhigh` defaults are all effective.

**Architecture:** Keep the current `.2` production container online while changing source in an isolated worktree. Add a pure model-selection helper that prefers Multi-Agent only when no valid user or restored-history selection exists, publish an immutable `.3` multi-architecture image through GitHub Actions, then repeat backup, constrained canary, cutover, and browser verification.

**Tech Stack:** React, TypeScript, Node test runner, GitHub Actions, GHCR, Docker Compose, Caddy, Playwright.

---

### Task 1: Default Model Regression

**Files:**
- Modify: `frontend/src/features/creative-console/creative-console-defaults.test.ts`
- Modify: `frontend/src/features/creative-console/creative-console-defaults.ts`
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx`
- Modify: `scripts/test-creative-console-customizations.mjs`

- [x] **Step 1: Write the failing tests**

Add a unit test where `grok-build-0.1` is first and `grok-4.20-multi-agent-0309` is later. Require the helper to select Multi-Agent, fall back to the first available route if Multi-Agent is absent, and return an empty string for an empty list. Add a source contract that requires the helper to be called from the chat fallback.

- [x] **Step 2: Verify the source contract fails**

Run:

```bash
node scripts/test-creative-console-customizations.mjs
```

Expected: FAIL because neither the preferred model constant nor `selectDefaultCreativeChatModel(modelGroups.chat)` exists.

- [x] **Step 3: Implement the minimal preference helper**

Add:

```ts
const preferredCreativeChatModel = "grok-4.20-multi-agent-0309";

export function selectDefaultCreativeChatModel(models: ReadonlyArray<{ publicId: string }>): string {
  return models.find((model) => model.publicId === preferredCreativeChatModel)?.publicId ?? models[0]?.publicId ?? "";
}
```

Use it only as the fallback after checking `selectedModels.chat`, preserving restored history and manual model selection.

- [x] **Step 4: Verify the source contract passes**

Run:

```bash
node scripts/test-creative-console-customizations.mjs
git diff --check
```

Expected: PASS with no whitespace errors. The real TypeScript unit test runs in GitHub Actions because this production host must not install the frontend dependency graph.

### Task 2: Aurora.3 Release Metadata

**Files:**
- Modify: `scripts/test_release_metadata.py`
- Modify: `scripts/verify-production-custom-release.sh`

- [x] **Step 1: Change the release metadata test first**

Require the verifier defaults to reference:

```text
/root/backups/grok2api-v3/v3.1.5-aurora.3-image-ref
/root/backups/grok2api-v3/pre-v3.1.5-aurora.3/account-count
```

- [x] **Step 2: Verify the metadata test fails**

Run:

```bash
python3 -m unittest -v scripts.test_release_metadata
```

Expected: FAIL because the verifier still points at `.2`.

- [x] **Step 3: Update verifier defaults and run lightweight regressions**

Change only the two default paths, then run:

```bash
node scripts/test-creative-console-customizations.mjs
python3 -m unittest -v scripts.test_system_instruction_proxy
python3 -m unittest -v scripts.test_ghcr_workflow
python3 -m unittest -v scripts.test_release_metadata
git diff --check
```

Expected: all tests pass.

### Task 3: Publish The Immutable Image

**Files:**
- Commit the Task 1 and Task 2 changes.
- Preserve tag `v3.1.5-aurora.2`; create tag `v3.1.5-aurora.3` on the hotfix commit.

- [x] **Step 1: Commit and push source**

Run:

```bash
git add frontend/src/features/creative-console/creative-console-defaults.test.ts \
  frontend/src/features/creative-console/creative-console-defaults.ts \
  frontend/src/features/creative-console/creative-console-page.tsx \
  scripts/test-creative-console-customizations.mjs \
  scripts/test_release_metadata.py \
  scripts/verify-production-custom-release.sh \
  docs/superpowers/plans/2026-08-27-v3-1-5-aurora-3-default-model-hotfix.md
git commit -m "fix: default Creative Console to Multi-Agent"
git push aurora HEAD:production-v3.1.5-aurora.1
```

- [ ] **Step 2: Verify the branch, publish the tag, and wait for GitHub Actions**

Require the production branch Verify, amd64, arm64, and manifest jobs to pass before creating and pushing annotated tag `v3.1.5-aurora.3`. Require the tag workflow to pass the same jobs, resolve the immutable manifest digest, and store the exact `tag@sha256` reference with mode `0600` at `/root/backups/grok2api-v3/v3.1.5-aurora.3-image-ref`.

### Task 4: Canary And Production Cutover

**Files:**
- Create: `/root/backups/grok2api-v3/pre-v3.1.5-aurora.3/`
- Modify: `/root/grok2api-v3/.env.production`
- Preserve: `/etc/caddy/Caddyfile`, `/root/grok.md`, database volume, browser-local history prefix, and SubBoost volumes.

- [ ] **Step 1: Check host resources and production health**

Run `nproc`, `uptime`, `free -h`, `swapon --show`, `df -h / /var/lib/docker`, the `.2` production verifier with explicit `.2` path overrides, and `docker stats --no-stream`. Do not compile or install dependencies on this host.

- [ ] **Step 2: Back up `.2` and run a constrained `.3` canary**

Use SQLite online backup, record the 200-account baseline, clone the data with UID/GID `10001:10001`, and run one canary limited to `192MiB` RAM, `384MiB` memory plus swap, `0.5` CPU, and `128` PIDs. Verify version, digest, database integrity, account count, and compiled frontend content, then stop the canary.

- [ ] **Step 3: Recreate only Grok2API**

Pin `.env.production` to the `.3` tag and digest, validate merged Compose, recreate only `grok2api`, wait for healthy, and leave Caddy, system instruction proxy, GrokSearch, and SubBoost unchanged.

- [ ] **Step 4: Verify production and browser behavior**

Run `scripts/verify-production-custom-release.sh`. In isolated Playwright contexts verify a fresh desktop and mobile conversation selects `grok-4.20-multi-agent-0309`, Web search is enabled, X search is enabled, reasoning is `xhigh`, new conversation preserves those defaults, history still restores messages, and `DEEIX CHAT` is absent.

- [ ] **Step 5: Roll back on any failure**

If health, database, proxy, or browser verification fails, restore the `.2` image reference from backup and recreate only `grok2api`. Do not alter `/root/grok.md`, Caddy routes, or SubBoost data during rollback.
