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
# OPENAI_API_KEY is NOT required here: both ops services reference the api
# service's key via ${{api.OPENAI_API_KEY}}, so it auto-tracks that key (incl.
# rotation). Only fill OPENAI_API_KEY below if you want a dedicated ops key that
# overrides the reference. RESEND_API_KEY and GITHUB_TOKEN have no other source
# and MUST be provided.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/../.secrets.env"
SERVICES=(oss-audit contrib-review)
REQUIRED_KEYS=(RESEND_API_KEY GITHUB_TOKEN)
OPTIONAL_KEYS=(OPENAI_API_KEY)

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
for k in "${REQUIRED_KEYS[@]}"; do
  if [ -z "${!k:-}" ]; then
    echo "ERROR: $k is empty in $ENV_FILE (required)" >&2
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 1

# Push every key that has a value; skip empty optional keys (e.g. OPENAI ref).
PUSH_KEYS=("${REQUIRED_KEYS[@]}")
for k in "${OPTIONAL_KEYS[@]}"; do
  [ -n "${!k:-}" ] && PUSH_KEYS+=("$k")
done

for svc in "${SERVICES[@]}"; do
  echo "-> $svc"
  for k in "${PUSH_KEYS[@]}"; do
    printf '%s' "${!k}" | railway variables --service "$svc" --skip-deploys --set-from-stdin "$k"
    echo "   set $k"
  done
done

echo
echo "Done. Secrets set on: ${SERVICES[*]}"
echo "Verify (values hidden):"
echo "  for s in ${SERVICES[*]}; do railway variables --service \"\$s\" --kv | grep -E '^(OPENAI_API_KEY|RESEND_API_KEY|GITHUB_TOKEN)=' | sed -E 's/=.*/=<set>/'; done"
