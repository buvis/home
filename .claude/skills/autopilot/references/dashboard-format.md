# Live Dashboard

The autopilot dashboard is provided by `pidash` (from buvis-gems).

## Usage

Run in a separate terminal pane while autopilot is working:

```bash
pidash [project-path]
```

Defaults to current directory. Watches `.local/prd-cycle.json` and updates in real time.

## What It Shows

- Phase pipeline: CATCHUP → PLANNING → WORKING → REVIEWING → DOUBT → DONE
- Task progress bar (during WORKING phase)
- Decision log (autonomous + pending)
- Review cycle history with severity counts

## Install

```bash
pip install buvis-gems[pidash]
# or
uv tool install buvis-gems[pidash]
```

## Batch Progress

When `batch` is present in the state file, pidash shows batch progress alongside per-PRD progress:

- Batch indicator: `{completed} PRDs done`
- Completed PRDs list with cycle counts

No extra action needed from autopilot — pidash reads the `batch` field automatically.

## No Action Required from Autopilot

Pidash watches the state file directly. As long as autopilot keeps `.local/prd-cycle.json` updated at phase transitions, the dashboard reflects current state automatically.
