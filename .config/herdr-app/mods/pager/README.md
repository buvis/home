# Pager

Herdr owns the presence probes, notification routing, and ntfy client here.
No Claude hooks or settings are needed by the migrated sender.

The selected layout must load `pager`. It sends desktop notifications while
present, or phone notifications after more than 300 seconds idle, while the
screensaver runs, or when the lid angle is below 70 degrees. Failed deliveries
use the existing bounded retries in `main.js`.

## Private configuration

`../../pager.local.json` is an ignored symlink to
`~/.local/.config/herdr-app/pager.local.json`. Keep the real file mode `0600`.
Provision it separately on each machine; never publish either its contents or
copies in dotfiles. Its string fields are:

- `url`: ntfy server URL.
- `topic`: notification topic.
- `credentials`: HTTP Basic credentials in `username:password` form; an empty
  string is supported for servers that deliberately allow anonymous publishing.

`NTFY_URL` and `NTFY_TOPIC` environment variables override the destination.
Missing or invalid private configuration fails phone delivery without logging
the configuration or falling back to Claude files. Desktop delivery does not
need this file.

## Machine dependencies

Python 3.10+, macOS `ioreg` and `pgrep`, `terminal-notifier`, mise, and a
mise-managed `pipx:pybooklid` installation with supported lid-sensor hardware.
The sender reports failure if the lid sensor cannot be read; this migration
does not add support for other operating systems or hardware.

Runtime delivery and presence diagnostics stay in `data/pager/`, outside this
mod. Keep that directory out of dotfiles.

## Verification

From the Herdr config directory:

```sh
python3 -B -m unittest discover -s mods/pager
herdr-app check mods/pager
```

Tests mock notifications and do not send messages. The import regression check
blocks reads under `.claude` to detect accidental reintroduction of that dependency.
