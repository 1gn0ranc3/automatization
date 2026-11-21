#!/bin/sh
set -eu
: "${ARTIFACTS:?Set ARTIFACTS to the report directory}"
# Полный прогон получает свой проект; ручной selenoid-up остаётся независимым.
SELENOID_PROJECT=${SELENOID_PROJECT:-selenoid-run-$$}
SELENOID_PORT=${SELENOID_PORT:-0}
export SELENOID_PROJECT SELENOID_PORT
mkdir -p "$ARTIFACTS"

compose() { docker compose -f compose.selenoid.yml "$@"; }
cleanup() {
    result=$?
    trap - EXIT
    cleanup_failed=0
    compose logs --no-color selenoid > "$ARTIFACTS/selenoid.log" 2>&1 || true
    # Selenoid создаёт браузеры вне Compose: убираем только сессии этого прогона.
    browsers=$(docker ps -aq --filter "label=qa.selenoid.project=$SELENOID_PROJECT") || {
        browsers=
        cleanup_failed=1
    }
    if [ -n "$browsers" ]; then
        docker rm -f $browsers || cleanup_failed=1
    fi
    compose down --timeout 15 || cleanup_failed=1
    if [ "$result" -eq 0 ] && [ "$cleanup_failed" -ne 0 ]; then
        result=1
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

compose --profile images pull chrome-image
compose build selenoid runner
compose up -d --wait selenoid
compose run --rm --user "$(id -u):$(id -g)" runner
