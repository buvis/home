#!/usr/bin/env bash

if [[ -f "${HOME}/.profile" ]]; then
  source "${HOME}/.profile"
fi

if [[ -f "${HOME}/.bashrc" ]]; then
  source "${HOME}/.bashrc"
fi

# Support kubectl plugins
export PATH="${PATH}:${HOME}/.krew/bin"
