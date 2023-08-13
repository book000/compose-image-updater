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

find "${PROJECTS_DIR}" -maxdepth 2 \( -name docker-compose.yml -or -name compose.yaml -or -name compose.yml \) -print0 | xargs -0 dirname | xargs -L1 basename | jq --raw-input --slurp 'split("\n")' > "${RESTARTABLE_PROJECTS_FILE}"
