#!/bin/bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 PROJECTS_DIR" >&2
    exit 2
fi

COMPOSE_IMAGE_UPDATER_DIR=$(cd -P -- "$(dirname -- "$0")" && printf '%s.' "$PWD")
COMPOSE_IMAGE_UPDATER_DIR=${COMPOSE_IMAGE_UPDATER_DIR%.}
PROJECTS_DIR=$(cd -P -- "$1" && printf '%s.' "$PWD")
PROJECTS_DIR=${PROJECTS_DIR%.}
RESTARTABLE_PROJECTS_FILE="${COMPOSE_IMAGE_UPDATER_DIR}/restartable_projects.json"
echo "Projects directory: ${PROJECTS_DIR}"
echo "Restartable projects file: ${RESTARTABLE_PROJECTS_FILE}"

WORK_DIR=$(mktemp -d)
trap 'rm -rf -- "$WORK_DIR"' EXIT
find "${PROJECTS_DIR}" -maxdepth 2 \( -type f -o -type l \) \( -name docker-compose.yml -o -name compose.yaml -o -name compose.yml \) -printf '%h\0' | sort -zu > "$WORK_DIR/projects"

while IFS= read -r -d '' project_dir; do
    printf '%s\0' "${project_dir##*/}"
done < "$WORK_DIR/projects" | jq --raw-input --slurp 'split("\u0000")[:-1] | unique' > "$WORK_DIR/restartables.json"

if [ -f "$RESTARTABLE_PROJECTS_FILE" ]; then
    echo "=== Changes in restartable projects ==="
    if diff -u -- "$RESTARTABLE_PROJECTS_FILE" "$WORK_DIR/restartables.json"; then
        echo "No changes detected."
    else
        status=$?
        if [ "$status" -ne 1 ]; then
            exit "$status"
        fi
    fi
    echo "========================================"
else
    echo "New restartable projects file created."
fi
mv -- "$WORK_DIR/restartables.json" "$RESTARTABLE_PROJECTS_FILE"
