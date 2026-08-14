# Hide DEEIX Chat Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the DEEIX Chat promotion from source and the pinned production frontend without compiling on the production host.

**Architecture:** Delete the source JSX block, then bind-mount a pinned-image-compatible HTML index containing a narrowly scoped CSS hide rule. A lightweight shell verifier covers source, overlay, and Compose wiring before deployment.

**Tech Stack:** React/TypeScript source, static HTML/CSS, Docker Compose, Bash, Caddy

---

### Task 1: Add A Failing Lightweight Verification

**Files:**
- Create: `scripts/verify-production-promotion-hidden.sh`

- [ ] **Step 1: Create the verifier**

The script must fail when the source still contains `DEEIX Chat`, require the overlay selector targeting the DEEIX repository link, require the read-only Compose mount, and run `docker compose config -q`.

- [ ] **Step 2: Verify RED**

Run: `bash scripts/verify-production-promotion-hidden.sh`

Expected: FAIL with `DEEIX Chat promotion remains in Creative Console source`.

### Task 2: Remove The Source Promotion And Add The Production Overlay

**Files:**
- Modify: `frontend/src/features/creative-console/creative-console-page.tsx`
- Create: `index.production.html`
- Modify: `docker-compose.production.yml`

- [ ] **Step 1: Delete the promotion `aside` from the Creative Console source**

Remove only the block containing the DEEIX Chat text and repository link. Leave the page header, mode tabs, and console panels unchanged.

- [ ] **Step 2: Create the pinned production index**

Copy the current pinned image's asset references and add this scoped rule in the document head:

```css
aside:has(> a[href="https://github.com/DEEIX-AI/DEEIX-Chat"]) {
  display: none !important;
}
```

- [ ] **Step 3: Mount the overlay read-only**

Add this service volume to `docker-compose.production.yml`:

```yaml
volumes:
  - "./index.production.html:/app/frontend/dist/index.html:ro"
```

- [ ] **Step 4: Verify GREEN**

Run: `bash scripts/verify-production-promotion-hidden.sh`

Expected: PASS with `promotion overlay verification passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify-production-promotion-hidden.sh frontend/src/features/creative-console/creative-console-page.tsx index.production.html docker-compose.production.yml
git commit -m "fix: hide Creative Console promotion"
```

### Task 3: Deploy And Verify Production

**Files:**
- No additional source files

- [ ] **Step 1: Record pre-deploy health**

Verify the container is healthy and `https://grok2api.xiaotianyo.com/healthz` returns 200.

- [ ] **Step 2: Recreate only the v3 service**

Run the production Compose `up -d --force-recreate grok2api` command and wait for `healthy`.

- [ ] **Step 3: Verify the mounted index and public response**

Assert the container mount is read-only, the public index includes the scoped CSS selector, and the pinned JavaScript and CSS assets return 200.

- [ ] **Step 4: Verify API compatibility and logs**

Assert health is 200, active and legacy keys return 200, an invalid key returns 401, and the recreated container has no error logs or secret values. Diagnose any startup warnings; a transient Statsig signer timeout is acceptable only when the signer becomes reachable, a Web request succeeds, and no warning repeats after recovery.
