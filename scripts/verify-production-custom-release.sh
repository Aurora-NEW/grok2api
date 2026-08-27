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
