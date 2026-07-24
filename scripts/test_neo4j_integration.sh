#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
COMPOSE_FILE="${REPOSITORY_ROOT}/docker-compose.integration.yml"
PYTHON_EXECUTABLE="${MEDSAFETY_PYTHON:-python}"

cleanup() {
  docker compose -f "${COMPOSE_FILE}" down
}
trap cleanup EXIT

docker compose -f "${COMPOSE_FILE}" up -d --wait

cd "${REPOSITORY_ROOT}"
MEDSAFETY_RUN_NEO4J_INTEGRATION=1 \
  "${PYTHON_EXECUTABLE}" -m pytest -q -m integration
