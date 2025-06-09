#!/bin/sh
COMPOSE_IMAGE_UPDATER_DIR=$(dirname "$0")
PROJECTS_DIR="$1"

echo "Projects directory: ${PROJECTS_DIR}"

RESTARTABLE_PROJECTS_FILE="${COMPOSE_IMAGE_UPDATER_DIR}/restartable_projects.json"

echo "Restartable projects file: ${RESTARTABLE_PROJECTS_FILE}"

# check if projects directory exists
if [ ! -d "${PROJECTS_DIR}" ]; then
    echo "Error: Projects directory[arg:1] does not exist"
    exit 1
fi

# Save old restartable projects file if it exists
OLD_RESTARTABLE_PROJECTS_FILE=""
if [ -f "${RESTARTABLE_PROJECTS_FILE}" ]; then
    OLD_RESTARTABLE_PROJECTS_FILE="${RESTARTABLE_PROJECTS_FILE}.old"
    cp "${RESTARTABLE_PROJECTS_FILE}" "${OLD_RESTARTABLE_PROJECTS_FILE}"
    echo "Backup of existing file created: ${OLD_RESTARTABLE_PROJECTS_FILE}"
fi

# Generate new restartable projects file
find "${PROJECTS_DIR}" -maxdepth 2 \( -name docker-compose.yml -or -name compose.yaml -or -name compose.yml \) -print0 | xargs -0 dirname | xargs -L1 basename | jq --raw-input --slurp 'split("\n")' > "${RESTARTABLE_PROJECTS_FILE}"

# Show diff if old file existed
if [ -f "${OLD_RESTARTABLE_PROJECTS_FILE}" ]; then
    echo ""
    echo "=== Changes in restartable projects ==="
    if diff -u "${OLD_RESTARTABLE_PROJECTS_FILE}" "${RESTARTABLE_PROJECTS_FILE}"; then
        echo "No changes detected."
    fi
    echo "========================================"
    
    # Clean up backup file
    rm "${OLD_RESTARTABLE_PROJECTS_FILE}"
else
    echo "New restartable projects file created."
fi
