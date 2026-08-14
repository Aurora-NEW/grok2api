#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_file="$repo_root/frontend/src/features/creative-console/creative-console-page.tsx"
migration_file="$repo_root/frontend/public/creative-console-chat-defaults-v1.js"
canonical_main_asset="$repo_root/frontend.production/index-DVIk9Mqh.js"
bootstrap_asset="$repo_root/frontend.production/index-entry-refresh-v3-20260814.js"
console_asset="$repo_root/frontend.production/creative-console-chat-defaults-v2-20260814.js"
compose_file="$repo_root/docker-compose.production.yml"
index_file="$repo_root/index.production.html"
caddy_file="${CADDY_CONFIG:-/etc/caddy/Caddyfile}"
base_url="${GROK2API_BASE_URL:-https://grok2api.xiaotianyo.com}"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

fixed_count() {
  local needle="$1"
  local file="$2"
  grep -oF "$needle" "$file" 2>/dev/null | wc -l | tr -d ' ' || true
}

check_hashes() {
  local local_file="$1"
  local relative_path="$2"
  local local_hash container_hash public_hash

  local_hash="$(sha256sum "$local_file" | awk '{print $1}')"
  container_hash="$(docker exec grok2api-v3 sha256sum "/app/frontend/dist/$relative_path" 2>/dev/null | awk '{print $1}')" \
    || fail "$relative_path is missing from the production container"
  public_hash="$(curl --silent --show-error --fail "$base_url/$relative_path" | sha256sum | awk '{print $1}')" \
    || fail "$relative_path is not available publicly"

  [[ "$container_hash" == "$local_hash" ]] || fail "$relative_path container hash mismatch"
  [[ "$public_hash" == "$local_hash" ]] || fail "$relative_path public hash mismatch"
}

node "$repo_root/scripts/test-creative-console-chat-defaults.mjs"
[[ -s "$migration_file" ]] || fail "migration script is missing"
[[ -s "$canonical_main_asset" ]] || fail "canonical main bundle is missing"
[[ -s "$bootstrap_asset" ]] || fail "entry refresh bootstrap is missing"
[[ -s "$console_asset" ]] || fail "versioned Creative Console bundle is missing"

new_defaults='reasoningEffort:`xhigh`,webSearch:!0,xSearch:!0'
old_defaults='reasoningEffort:`auto`,webSearch:!1,xSearch:!1'
clear_reset='ne(e.promptCacheKey),T(e.reasoningEffort),S(e.webSearch),w(e.xSearch),L(``)'
old_clear='ne(e.promptCacheKey),L(``)'
stored_defaults='reasoningEffort:Fi(e.reasoningEffort)?e.reasoningEffort:`auto`,webSearch:e.webSearch===!0,xSearch:e.xSearch===!0'
forced_switch='T(`xhigh`),S(!0),w(!0)'
stored_switch='T(i.reasoningEffort),S(i.webSearch),w(i.xSearch)'

[[ "$(fixed_count "$new_defaults" "$console_asset")" == 2 ]] \
  || fail "production bundle does not force blank and stored-session defaults"
[[ "$(fixed_count "$old_defaults" "$console_asset")" == 0 ]] \
  || fail "production bundle still contains the old defaults"
[[ "$(fixed_count "$clear_reset" "$console_asset")" == 2 ]] \
  || fail "production bundle does not contain both reset paths"
[[ "$(fixed_count "$old_clear" "$console_asset")" == 0 ]] \
  || fail "production bundle still contains the old clear path"
[[ "$(fixed_count "$stored_defaults" "$console_asset")" == 0 ]] \
  || fail "production bundle still restores saved defaults"
[[ "$(fixed_count "$forced_switch" "$console_asset")" == 1 ]] \
  || fail "production bundle does not force defaults when switching history"
[[ "$(fixed_count "$stored_switch" "$console_asset")" == 0 ]] \
  || fail "production bundle still restores settings when switching history"
[[ "$(fixed_count 'creative-console-search-defaults-v1-20260814.js' "$canonical_main_asset")" == 0 ]] \
  || fail "main bundle still references the v1 Creative Console chunk"
[[ "$(fixed_count 'creative-console-chat-defaults-v2-20260814.js' "$canonical_main_asset")" == 2 ]] \
  || fail "main bundle does not contain both versioned lazy-chunk references"
grep -Fq 'fetch(canonicalEntry, { cache: "reload" })' "$bootstrap_asset" \
  || fail "entry bootstrap does not force a one-time canonical entry refresh"
grep -Fq 'import(canonicalEntry)' "$bootstrap_asset" \
  || fail "entry bootstrap does not import the canonical module URL"

grep -Fq './frontend/public/creative-console-chat-defaults-v1.js:/app/frontend/dist/creative-console-chat-defaults-v1.js:ro' "$compose_file" \
  || fail "migration mount is missing"
grep -Fq './frontend.production/index-DVIk9Mqh.js:/app/frontend/dist/assets/index-DVIk9Mqh.js:ro' "$compose_file" \
  || fail "canonical main bundle mount is missing"
grep -Fq './frontend.production/index-entry-refresh-v3-20260814.js:/app/frontend/dist/assets/index-entry-refresh-v3-20260814.js:ro' "$compose_file" \
  || fail "entry refresh bootstrap mount is missing"
grep -Fq './frontend.production/creative-console-chat-defaults-v2-20260814.js:/app/frontend/dist/assets/creative-console-chat-defaults-v2-20260814.js:ro' "$compose_file" \
  || fail "Creative Console bundle mount is missing"
grep -Fq '@canonical_frontend_entry path /assets/index-DVIk9Mqh.js' "$caddy_file" \
  || fail "canonical frontend entry cache matcher is missing"
grep -Fq 'Cache-Control "no-cache"' "$caddy_file" \
  || fail "canonical frontend entry no-cache policy is missing"

node --check "$migration_file"
node --input-type=module --check < "$canonical_main_asset"
node --input-type=module --check < "$bootstrap_asset"
node --input-type=module --check < "$console_asset"
node --input-type=module - "$index_file" <<'NODE'
import fs from "node:fs";

const html = fs.readFileSync(process.argv[2], "utf8");
const migration = html.indexOf("/creative-console-chat-defaults-v1.js");
const entrypoint = html.indexOf("/assets/index-entry-refresh-v3-20260814.js");
if (migration < 0 || entrypoint < 0 || migration >= entrypoint) process.exit(1);
if (html.includes('/assets/index-chat-defaults-v2-20260814.js')) process.exit(1);
NODE

check_hashes "$migration_file" "creative-console-chat-defaults-v1.js"
check_hashes "$canonical_main_asset" "assets/index-DVIk9Mqh.js"
check_hashes "$bootstrap_asset" "assets/index-entry-refresh-v3-20260814.js"
check_hashes "$console_asset" "assets/creative-console-chat-defaults-v2-20260814.js"

canonical_cache_control="$(curl --silent --show-error --fail --head "$base_url/assets/index-DVIk9Mqh.js" \
  | tr -d '\r' | awk -F': ' 'tolower($1) == "cache-control" { print tolower($2) }')" \
  || fail "canonical entry cache headers are unavailable"
[[ "$canonical_cache_control" == *"no-cache"* ]] \
  || fail "canonical entry is still served without no-cache (got: $canonical_cache_control)"

public_html="$(curl --silent --show-error --fail "$base_url/creative-console")" \
  || fail "public Creative Console HTML is unavailable"
case "$public_html" in
  *'/creative-console-chat-defaults-v1.js'*'/assets/index-entry-refresh-v3-20260814.js'*) ;;
  *) fail "public HTML does not load migration before the v3 entry bootstrap" ;;
esac
[[ "$public_html" != *'/assets/index-chat-defaults-v2-20260814.js'* ]] \
  || fail "public HTML still loads the non-canonical v2 main module directly"

printf 'production chat defaults verification passed\n'
