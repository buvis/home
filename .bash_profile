#!/usr/bin/env bash

# Detect OS
UNAME_BIN=$(command -v uname)

case $("${UNAME_BIN}" | tr '[:upper:]' '[:lower:]') in
  linux*)
    if [[ $("${UNAME_BIN}" -r) =~ ^microsoft ]]; then
        IS_WSL=true
    else
        IS_LINUX=true
    fi
    ;;
  darwin*)
    IS_MAC=true
    ;;
  msys*|cygwin*|mingw*|nt|win*)
    IS_WIN=true
    ;;
esac

# Prefer GNU utils on Mac
if [[ $IS_MAC ]]; then
    export PATH="/usr/local/opt/grep/libexec/gnubin:$PATH"
    export PATH="/usr/local/opt/coreutils/libexec/gnubin:$PATH"
fi

if [[ -f "${HOME}/.profile" ]]; then
    source "${HOME}/.profile"
fi

if [[ -f "${HOME}/.bashrc" ]]; then
    source "${HOME}/.bashrc"
fi
