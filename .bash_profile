#!/usr/bin/env bash

if [[ -f "${HOME}/.profile" ]]; then
    source "${HOME}/.profile"
fi

if [[ -f "${HOME}/.bashrc" ]]; then
    source "${HOME}/.bashrc"
fi

# Prefer stuff installed by homebrew
export PATH=/usr/local/opt/coreutils/libexec/gnubin:/usr/local/bin:$PATH
