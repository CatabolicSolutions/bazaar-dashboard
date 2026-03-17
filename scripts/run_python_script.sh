#!/bin/bash
set -e

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <python-script> [args...]" >&2
  exit 1
fi

PYTHON_SCRIPT="$1"
shift

bash -ic '
source "$HOME/.profile" 2>/dev/null || true
source "$HOME/.bashrc" 2>/dev/null || true
source "$HOME/alfred_env/bin/activate"
python "$1" "${@:2}"
deactivate
' bash "$PYTHON_SCRIPT" "$@"
