#!/usr/bin/env bash
set -euo pipefail

base_url="${GROK2API_BASE_URL:-https://grok2api.xiaotianyo.com}"
active_key_file="${GROK2API_ACTIVE_KEY_FILE:-/root/grok2api-v3/.client-key}"
compat_env="${GROK2API_COMPAT_ENV:-/etc/caddy/grok2api-compat.env}"
grok_search_env="${GROK_SEARCH_ENV:-/root/GrokSearch/.env}"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

expect_status() {
  local label="$1"
  local expected="$2"
  shift 2
  local actual
  actual="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$@")"
  [[ "$actual" == "$expected" ]] || fail "$label returned HTTP $actual, expected $expected"
  printf 'ok: %s (%s)\n' "$label" "$actual"
}

systemctl is-active --quiet grok-system-instruction-proxy.service || fail "instruction proxy service is not active"
systemctl is-active --quiet caddy.service || fail "Caddy is not active"
systemctl is-active --quiet grok-search.service || fail "GrokSearch is not active"

curl --silent --show-error --fail http://127.0.0.1:8001/_system-instruction/health \
  | python3 -c 'import json, sys; assert json.load(sys.stdin) == {"status": "ok"}' \
  || fail "instruction proxy health response is invalid"
printf 'ok: instruction proxy health\n'

caddy validate --config /etc/caddy/Caddyfile >/dev/null
printf 'ok: Caddy configuration\n'

[[ -s "$active_key_file" ]] || fail "active client key file is missing"
[[ -s "$compat_env" ]] || fail "Caddy compatibility environment is missing"
active_key="$(tr -d '\r\n' < "$active_key_file")"
set -a
# shellcheck disable=SC1090
. "$compat_env"
set +a
[[ -n "${GROK2API_LEGACY_API_KEY:-}" ]] || fail "legacy API key is not configured"

expect_status "public root" 200 "$base_url/"
expect_status "public health" 200 "$base_url/health"
expect_status "active key model list" 200 -H "Authorization: Bearer $active_key" "$base_url/v1/models"
expect_status "legacy key model list" 200 -H "Authorization: Bearer $GROK2API_LEGACY_API_KEY" "$base_url/v1/models"
expect_status "invalid key rejection" 401 -H "Authorization: Bearer invalid-system-instruction-check" "$base_url/v1/models"
expect_status "proxy model passthrough" 200 -H "Authorization: Bearer $active_key" http://127.0.0.1:8001/v1/models

check_injection_route() {
  local label="$1"
  local path="$2"
  local payload="$3"
  shift 3
  local headers
  local status
  headers="$(mktemp)"
  trap 'rm -f "$headers"' RETURN
  status="$(curl --silent --show-error --dump-header "$headers" --output /dev/null --write-out '%{http_code}' \
    -H 'Authorization: Bearer invalid-system-instruction-check' \
    -H 'Content-Type: application/json' \
    "$@" \
    --data-binary "$payload" \
    "$base_url$path")"
  [[ "$status" == "401" ]] || fail "$label returned HTTP $status, expected 401"
  tr -d '\r' < "$headers" | grep -qi '^X-System-Instruction-Applied: 1$' \
    || fail "$label response did not confirm instruction injection"
  rm -f "$headers"
  trap - RETURN
  printf 'ok: %s (injected, auth rejected)\n' "$label"
}

check_injection_route \
  "Responses route" "/v1/responses" \
  '{"model":"grok-chat-fast","input":"health check"}'
check_injection_route \
  "Chat Completions route" "/v1/chat/completions" \
  '{"model":"grok-chat-fast","messages":[{"role":"user","content":"health check"}]}'
check_injection_route \
  "Anthropic Messages route" "/v1/messages" \
  '{"model":"grok-chat-fast","max_tokens":1,"messages":[{"role":"user","content":"health check"}]}' \
  -H 'anthropic-version: 2023-06-01'

grep -qx 'GROK_API_URL=http://127.0.0.1:8001/v1' "$grok_search_env" \
  || fail "GrokSearch is not routed through the instruction proxy"
printf 'ok: GrokSearch route\n'

printf 'production system instruction verification passed\n'
