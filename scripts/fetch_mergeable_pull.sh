#!/usr/bin/env bash

set -euo pipefail

readonly repository="MahdiHedhli/LITB"
readonly pull_request_number="${1:?pull request number is required}"
readonly destination="${2:?destination is required}"

if [[ ! "${pull_request_number}" =~ ^[1-9][0-9]*$ ]]; then
  echo "pull request number is malformed" >&2
  exit 1
fi

for attempt in 1 2 3 4 5; do
  if gh api "repos/${repository}/pulls/${pull_request_number}" \
      > "${destination}" &&
    jq -e '
      .mergeable == true and
      (
        .mergeable_state == "blocked" or
        .mergeable_state == "clean" or
        .mergeable_state == "unstable"
      )
    ' "${destination}" > /dev/null; then
    exit 0
  fi
  if [ "${attempt}" -lt 5 ]; then
    sleep 2
  fi
done

exit 1
