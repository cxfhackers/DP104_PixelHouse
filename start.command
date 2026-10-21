#!/bin/zsh
set -e
cd "${0:A:h}"

if [[ ! -x .venv/bin/python ]]; then
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null 2>&1; then
      "$candidate" -m venv .venv
      break
    fi
  done
fi

if [[ ! -x .venv/bin/python ]]; then
  echo '需要 Python 3.11+。Homebrew 示例：brew install python@3.12'
  read '?按回车退出…'
  exit 1
fi

if ! .venv/bin/python -c 'import hid, serial, PIL, requests, PySide6.QtWebEngineWidgets' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python app_qt.py "$@"
