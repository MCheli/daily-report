#!/usr/bin/env bash
# Push the daily-report secrets from your local .env to the homelab,
# without ever putting the values in a chat or shell history.
#
# Usage:
#   ./scripts/upload-secrets.sh <ssh-target>
# Example:
#   ./scripts/upload-secrets.sh mcheli@83rr-poweredge.local
#
# What it does:
#   1. Extracts ONLY the keys daily-report needs from this repo's .env
#   2. scp's them to /tmp/daily-report.env on the target
#   3. Tells you the exact one-liner to merge into ~/83rr-poweredge/.env
#      (so the agent on the server can do the merge without ever seeing
#       the values in its prompt)
#
# After deployment, run on the homelab:
#   shred -u /tmp/daily-report.env

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <ssh-target>"
  echo "  e.g. $0 mcheli@83rr-poweredge.local"
  exit 1
fi

target="$1"
src="$(cd "$(dirname "$0")/.." && pwd)/.env"
remote_path="/tmp/daily-report.env"

if [[ ! -f "$src" ]]; then
  echo "no $src found locally - copy .env.example to .env and fill in first"
  exit 1
fi

# The keys the daily-report container reads. Anything else in the local
# .env (e.g. dev-only overrides) is filtered out.
keys=(
  ANTHROPIC_API_KEY
  TALLIED_API_KEY
  TASKS_API_KEY
  HOME_ASSISTANT_TOKEN
  CALENDAR_ICS_URL
  DAILY_REPORT_API_TOKEN
)

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

echo "# Uploaded by upload-secrets.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$tmp"
for k in "${keys[@]}"; do
  line=$(grep -E "^${k}=" "$src" || true)
  if [[ -z "$line" ]]; then
    echo "  WARN: $k not found in $src - skipping" >&2
    continue
  fi
  echo "$line" >> "$tmp"
done

scp -q "$tmp" "${target}:${remote_path}"
ssh -q "$target" "chmod 600 ${remote_path}"

cat <<EOF
Uploaded $(wc -l < "$tmp") lines to ${target}:${remote_path}

Now hand DEPLOYMENT.md to your agent on the homelab. When it gets to
the "Environment" step it can run:

    while IFS= read -r line; do
      [[ \$line =~ ^# ]] && continue
      [[ -z \$line ]]   && continue
      key=\${line%%=*}
      grep -q "^\${key}=" ~/83rr-poweredge/.env \\
        && sed -i "s|^\${key}=.*|\${line}|" ~/83rr-poweredge/.env \\
        || echo "\$line" >> ~/83rr-poweredge/.env
    done < ${remote_path}

After verifying the daily-report container starts cleanly:

    shred -u ${remote_path}
EOF
