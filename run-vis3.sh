#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir/backend"
exec "$project_dir/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 1997
