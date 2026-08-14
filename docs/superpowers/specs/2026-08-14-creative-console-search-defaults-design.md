# Creative Console Search Defaults Design

## Goal

Make Creative Console chat use Web Search and X Search enabled and reasoning effort set to `xhigh` whenever a conversation is restored, created, cleared, or selected. Manual changes only apply to the currently open conversation state.

## Current Behavior

Chat settings are stored per client key in browser `localStorage`. Restoring or selecting an existing session previously copied its saved `auto/off/off` values into React state, so blank-session defaults and a one-time migration could later be undone by stale browser state.

The Console route for upstream model `grok-4.20-0309-reasoning` is intentionally fixed to `auto`; this model remains the only exception.

## Design

1. Change blank chat sessions to default to `webSearch: true`, `xSearch: true`, and `reasoningEffort: "xhigh"`.
2. Make both New Conversation and Clear Conversation copy all three settings from the new blank session into active UI state.
3. Normalize every parsed stored session to the new defaults instead of restoring its saved search and reasoning values.
4. Apply the new defaults again whenever the user selects a different saved conversation. Manual changes remain usable until reload, clear, new conversation, or history selection.
5. Keep the browser migration script for compatibility with already-open v1 pages, while runtime normalization is the authoritative behavior.

## Production Deployment

The production host must not compile the frontend. Patch and pin the currently deployed main and Creative Console bundles, and mount them read-only through the production Compose overlay. Serve the small migration script as a separate pinned public file before the module entrypoint.

The Creative Console lazy chunk uses a new versioned filename. The main bundle must retain its canonical `/assets/index-DVIk9Mqh.js` URL because existing lazy chunks import that exact module and share its React context. Loading a renamed copy as the entrypoint creates a second module instance, breaks `AuthProvider`, and can render the old chat defaults.

Use a small versioned bootstrap module to fetch the canonical entry once with `cache: "reload"`, consume the response, record a browser marker, and then import the canonical URL. Serve the canonical entry with `Cache-Control: no-cache` so later fixes are revalidated without clearing cookies, login state, or chat history.

## Verification

- Verify source defaults, both reset paths, stored-session parsing, and history selection.
- Confirm saved `auto/off/off` values are never restored into active runtime state.
- Syntax-check the migration script and patched ES modules without running a build.
- Confirm local, container, and public asset hashes match.
- Confirm public HTML loads the migration before the versioned entry bootstrap.
- Confirm the canonical main bundle is served with `no-cache` and imports the versioned Creative Console chunk.
- Run a constrained real-browser check with a saved `auto/off/off` session and verify initial and post-New Conversation controls both report `xhigh/on/on`, without React context errors.
- Recheck the container, Caddy, Grok Search, system-instruction proxy, authentication routes, and public endpoints after the single-container recreate.
