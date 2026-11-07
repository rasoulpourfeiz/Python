#!/bin/bash
# Double-click to build KardexApp.app (output: dist/KardexApp.app). Run on a Mac.
cd "$(dirname "$0")" || exit 1

find_python() {
  local cands=() v c
  for v in 3.13 3.12 3.14 3.11 3.15 3.10; do
    cands+=("/Library/Frameworks/Python.framework/Versions/$v/bin/python3" "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v")
  done
  cands+=("$HOME/.pyenv/shims/python3" "/opt/homebrew/bin/python3" "/usr/local/bin/python3")
  c="$(command -v python3 2>/dev/null)"
  # /usr/bin/python3 on a Mac without Xcode tools is only a stub that pops up an installer: skip it then
  if [ -n "$c" ]; then
    if [ "$c" != "/usr/bin/python3" ] || [ "$(uname)" != "Darwin" ] || xcode-select -p >/dev/null 2>&1; then cands+=("$c"); fi
  fi
  FOUND=""
  for p in "${cands[@]}"; do
    [ -x "$p" ] || continue
    FOUND="$FOUND\n  $p -> $("$p" --version 2>&1)"
    if "$p" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,16) else 1)' 2>/dev/null; then echo "$p"; return 0; fi
  done
  return 1
}
no_python() {
  echo "No suitable Python (3.10 - 3.15) was found on this Mac."
  [ -n "$FOUND" ] && printf "Pythons that were found but are not supported:$FOUND\n"
  echo "Install Python 3.12 (macOS 64-bit universal2 installer) from https://www.python.org/downloads/macos/"
  echo "then double-click this file again. Opening the download page now..."
  open "https://www.python.org/downloads/macos/"
  read -r -p "Press Enter to close..." _; exit 1
}

PY="$(find_python)"
if [ -z "$PY" ]; then no_python; fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements-build.txt || { read -r -p "Install failed. Press Enter..." _; exit 1; }
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name KardexApp --osx-bundle-identifier ir.kardex.app main.py \
  || { read -r -p "Build failed. Press Enter..." _; exit 1; }
echo; echo "Done: $(pwd)/dist/KardexApp.app"
open dist
read -r -p "Press Enter to close..." _
