#!/bin/sh
set -e

PROJECTS_DIR="$1"
LOG_DIR="$2"

echo "Projects directory: ${PROJECTS_DIR}"
echo "Log directory: ${LOG_DIR}"

# check if projects directory is specified
if [ -z "${PROJECTS_DIR}" ]; then
    echo "Error: Projects directory[arg:1] is not specified"
    exit 1
fi

# check if log directory is specified
if [ -z "${LOG_DIR}" ]; then
    echo "Error: Log directory[arg:2] is not specified"
    exit 1
fi

# check if projects directory exists
if [ ! -d "${PROJECTS_DIR}" ]; then
    echo "Error: Projects directory[arg:1] does not exist"
    exit 1
fi

# check if log directory exists
if [ ! -d "${LOG_DIR}" ]; then
  mkdir -p "${LOG_DIR}"
fi

DATETIME=$(date '+%Y%m%d_%H%M%S')
find "${PROJECTS_DIR}" -maxdepth 2 -name docker-compose.yml -print0 | xargs -0 dirname | xargs -L1 /mnt/hdd/compose-image-updater/wrapper.sh 2>&1 | tee "${LOG_DIR}/${DATETIME}.log"
