# Changelog

All notable changes to this repo are documented in this file. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **install**: stamp-based gating helpers (`should_skip`, `stamp_step`) under `$XDG_CACHE_HOME/buvis/`
- **install**: skip `sysup nvim` when the stamp is newer than 24 hours, cutting repeat-install time on Koolna pod restarts
- **install**: skip the Claude CLI installer when `claude` is already on `$PATH`
- **install**: default cache env vars (`XDG_CACHE_HOME`, `UV_CACHE_DIR`, `PIP_CACHE_DIR`, `CARGO_HOME`, `npm_config_cache`, `MISE_CACHE_DIR`) exported when unset so reruns on a bare host still cache correctly

### Changed

- **install**: use committed submodule SHAs via `submodule update --init --recursive`; stop floating submodules with `--remote --merge`
