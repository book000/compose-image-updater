#!/bin/sh
set -e

if [ $# != 1 ]; then
    cwd="${PWD}"
else
    cwd="$1"
fi
echo "Target directory: ${cwd}"

# Change to the directory where the script is located
cd "$(dirname "$0")" || exit 1

# Load webhook url from file
if [ -f 'discord_webhook_url.txt' ]; then
    CIU_DISCORD_WEBHOOK_URL="$(cat discord_webhook_url.txt)"
    export CIU_DISCORD_WEBHOOK_URL
fi

# venv
if [ -d venv ]; then
    # shellcheck disable=SC1091
    . venv/bin/activate
else
    python3 -m venv venv
    # shellcheck disable=SC1091
    . venv/bin/activate
fi

# Install requirements
pip install -r requirements.txt

# Run the update script
if ! python3 -m src "${cwd}"; then
    echo "Error: Failed to run the script"
    exit 1
fi

# Change back to the original directory
cd "${cwd}" || exit 1
