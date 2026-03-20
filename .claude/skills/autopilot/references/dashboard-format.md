# Live Dashboard

The autopilot dashboard is provided by `pidash` (from buvis-gems).

## Usage

Run in a separate terminal pane while autopilot is working:

```bash
pidash [project-path]
```

Defaults to current directory. Watches `.local/prd-cycle.json` and updates in real time.

## What It Shows

- Phase pipeline: CATCHUP → PLANNING → WORKING → REVIEWING → DONE
- Task progress bar (during WORKING phase)
- Decision log (autonomous + pending)
- Review cycle history with severity counts

## Install

```bash
pip install buvis-gems[pidash]
# or
uv tool install buvis-gems[pidash]
```

## No Action Required from Autopilot

Pidash watches the state file directly. As long as autopilot keeps `.local/prd-cycle.json` updated at phase transitions, the dashboard reflects current state automatically.
