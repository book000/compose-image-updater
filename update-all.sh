#!/bin/bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 PROJECTS_DIR LOG_DIR" >&2
    exit 2
fi

COMPOSE_IMAGE_UPDATER_DIR=$(cd -P -- "$(dirname -- "$0")" && printf '%s.' "$PWD")
COMPOSE_IMAGE_UPDATER_DIR=${COMPOSE_IMAGE_UPDATER_DIR%.}
PROJECTS_DIR=$(cd -P -- "$1" && printf '%s.' "$PWD")
PROJECTS_DIR=${PROJECTS_DIR%.}
LOG_DIR="$2"
if [ -z "$LOG_DIR" ]; then
    echo "Error: Log directory[arg:2] is not specified" >&2
    exit 2
fi

echo "Projects directory: ${PROJECTS_DIR}"
echo "Log directory: ${LOG_DIR}"
mkdir -p -- "${LOG_DIR}"

PROJECT_LIST=$(mktemp)
trap 'rm -f -- "$PROJECT_LIST"' EXIT
find "${PROJECTS_DIR}" -maxdepth 2 \( -type f -o -type l \) \( -name docker-compose.yml -o -name compose.yaml -o -name compose.yml \) -printf '%h\0' | sort -zu > "$PROJECT_LIST"

run_projects() {
    local status=0 wrapper_status project_dir
    while IFS= read -r -d '' project_dir <&3; do
        if "${COMPOSE_IMAGE_UPDATER_DIR}/wrapper.sh" "$project_dir"; then
            :
        else
            wrapper_status=$?
            if [ "$status" -eq 0 ]; then
                status=$wrapper_status
            fi
        fi
    done 3< "$PROJECT_LIST"
    return "$status"
}

DATETIME=$(date '+%Y%m%d_%H%M%S')
run_projects 2>&1 | tee -- "${LOG_DIR}/${DATETIME}.log"
