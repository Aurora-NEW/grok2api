#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
source_file="$repo_root/frontend/src/features/creative-console/creative-console-page.tsx"
overlay_file="$repo_root/index.production.html"
compose_override="$repo_root/docker-compose.production.yml"

if rg -q 'DEEIX Chat|DEEIX-AI/DEEIX-Chat' "$source_file"; then
  echo "DEEIX Chat promotion remains in Creative Console source" >&2
  exit 1
fi

grep -Fq 'aside:has(> a[href="https://github.com/DEEIX-AI/DEEIX-Chat"])' "$overlay_file"
grep -Fq './index.production.html:/app/frontend/dist/index.html:ro' "$compose_override"

docker compose \
  -p grok2api-v3 \
  -f "$repo_root/docker-compose.yml" \
  -f "$compose_override" \
  --env-file "$repo_root/.env.production" \
  config -q

echo "promotion overlay verification passed"
