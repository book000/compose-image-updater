#!/bin/bash
set -euo pipefail

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [PROJECT_DIR]" >&2
    exit 2
fi

if [ "$#" -eq 0 ]; then
    cwd="$PWD"
else
    cwd="$1"
fi
cwd=$(cd -P -- "$cwd" && printf '%s.' "$PWD")
cwd=${cwd%.}
echo "Target directory: ${cwd}"

cd -- "$(dirname -- "$0")"

if [ -f 'discord_webhook_url.txt' ]; then
    CIU_DISCORD_WEBHOOK_URL="$(cat discord_webhook_url.txt)"
    export CIU_DISCORD_WEBHOOK_URL
fi

if [ ! -d venv ]; then
    python3 -m venv venv
fi
# shellcheck disable=SC1091
. venv/bin/activate

pip install -r requirements.txt

if python3 -m src "${cwd}"; then
    exit 0
else
    status=$?
    echo "Error: Failed to run the script" >&2
    exit "$status"
fi
