#!/usr/bin/env bash
#
# Push ops secrets to both Railway cron services in one shot.
#
# Usage:
#   1. cp ops/.secrets.env.example ops/.secrets.env
#   2. Fill ops/.secrets.env with ROTATED keys (the ones first pasted in chat
#      are burned — generate fresh ones before using them here).
#   3. ./ops/scripts/set-secrets.sh
#
# ops/.secrets.env is gitignored. It never gets committed. Values are piped to
# the Railway CLI via stdin, so they don't appear in `ps` output or shell history.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/../.secrets.env"
SERVICES=(oss-audit contrib-review)
KEYS=(OPENAI_API_KEY RESEND_API_KEY GITHUB_TOKEN)

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found." >&2
  echo "  cp ops/.secrets.env.example ops/.secrets.env  and fill it first." >&2
  exit 1
fi

# Load the file into this shell only (not exported to children except via stdin below).
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

missing=0
for k in "${KEYS[@]}"; do
  if [ -z "${!k:-}" ]; then
    echo "ERROR: $k is empty in $ENV_FILE" >&2
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 1

for svc in "${SERVICES[@]}"; do
  echo "-> $svc"
  for k in "${KEYS[@]}"; do
    printf '%s' "${!k}" | railway variables --service "$svc" --skip-deploys --set-from-stdin "$k"
    echo "   set $k"
  done
done

echo
echo "Done. Secrets set on: ${SERVICES[*]}"
echo "Verify (values hidden):"
echo "  for s in ${SERVICES[*]}; do railway variables --service \"\$s\" --kv | grep -E '^(OPENAI_API_KEY|RESEND_API_KEY|GITHUB_TOKEN)=' | sed -E 's/=.*/=<set>/'; done"
