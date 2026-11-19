#!/usr/bin/env bash
# Put both sites back to the starting state: PHP 8.1, fresh content, no snapshots.
set -euo pipefail
cd "$(dirname "$0")"
uvx podman-compose down -v
rm -rf snapshots
uvx podman-compose up -d
./seed.sh
