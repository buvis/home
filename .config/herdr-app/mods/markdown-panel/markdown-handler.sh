#!/bin/sh
set -eu

APP="$HOME/Applications/Kanso Markdown.app"
ID="dev.kanso.markdown"
HOME_DIR="${HERDR_APP_HOME:-$HOME/.config/herdr-app}"
INBOX="$HOME_DIR/data/kanso-open"
SAVED="$HOME_DIR/data/kanso-markdown-previous"
TYPES="net.daringfireball.markdown"
LINUX_TYPES="text/markdown text/x-markdown text/plain"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_APPS="$DATA_HOME/applications"
OPENER="$DATA_HOME/kanso-markdown/open.sh"
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

handler() {
  if [ $# -eq 0 ]; then
    swift - <<'SWIFT' 2>/dev/null
import Foundation
import CoreServices
if let id = LSCopyDefaultRoleHandlerForContentType("net.daringfireball.markdown" as CFString, .all)?.takeRetainedValue() { print(id) }
SWIFT
  else
    swift - "$1" <<'SWIFT'
import Foundation
import CoreServices
let id = CommandLine.arguments[1] as NSString as CFString
let status = LSSetDefaultRoleHandlerForContentType("net.daringfireball.markdown" as CFString, .all, id)
if status != 0 { print("LaunchServices refused (\(status))"); exit(1) }
SWIFT
  fi
}

hand_to_herdr() {
  cat <<HAND
mkdir -p "$INBOX"
printf '%s' "\$p" > "$INBOX/\$(date +%s)-\$\$.path"
s=\$("$herdr" status 2>/dev/null)
case "\$s" in
  *'"layout": "kanso"'*) ;;
  *) if [ -d "$HOME_DIR/mods/markdown-panel" ]; then
       case "\$s" in *'"markdown-panel"'*) ;; *) "$herdr" do mod.open '{"name":"markdown-panel"}' >/dev/null 2>&1 ;; esac
     fi ;;
esac
HAND
}

announce() {
  if [ "$1" = "$2" ]; then echo "Kanso Markdown is updated; .md files still open in Herdr."
  else echo "Markdown files now open in Herdr (they opened in ${1:-the system default})."; fi
}

refresh_desktop() {
  command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_APPS" >/dev/null 2>&1 || true
}

install() {
  command -v swift >/dev/null || { echo "Needs swift (Xcode or its Command Line Tools)." >&2; exit 1; }
  herdr=$(command -v herdr-app || echo "$HOME/.local/bin/herdr-app")
  script=$(mktemp "${TMPDIR:-/tmp}/kanso-markdown.XXXXXX")
  cat > "$script" <<'APPLESCRIPT'
on open theItems
	set opener to POSIX path of (path to me) & "Contents/Resources/open.sh"
	repeat with f in theItems
		do shell script "/bin/sh " & quoted form of opener & " " & quoted form of (POSIX path of f)
	end repeat
end open
on run
	display dialog "Kanso Markdown opens .md files in Herdr. Open a Markdown file to use it." buttons {"OK"} default button 1
end run
APPLESCRIPT
  mkdir -p "$HOME/Applications"
  rm -rf "$APP"
  osacompile -o "$APP" "$script"
  rm -f "$script"
  cat > "$APP/Contents/Resources/open.sh" <<OPEN
#!/bin/sh
p=\$1
export HERDR_APP_HOME="$HOME_DIR"
/usr/bin/pgrep -xq Herdr || exec /usr/bin/open -a TextEdit "\$p"
$(hand_to_herdr)
/usr/bin/open -a Herdr
OPEN
  plist="$APP/Contents/Info.plist"
  plutil -replace CFBundleIdentifier -string "$ID" "$plist"
  plutil -replace CFBundleName -string "Kanso Markdown" "$plist"
  plutil -replace LSUIElement -bool true "$plist"
  plutil -replace CFBundleDocumentTypes -json "[{\"CFBundleTypeName\":\"Markdown\",\"CFBundleTypeRole\":\"Editor\",\"LSHandlerRank\":\"Alternate\",\"LSItemContentTypes\":[\"$TYPES\"]}]" "$plist"
  codesign --force --sign - "$APP" >/dev/null 2>&1 || true
  "$LSREGISTER" -f "$APP"
  mkdir -p "$INBOX"
  previous=$(handler || true)
  if [ -n "$previous" ] && [ "$previous" != "$ID" ]; then printf '%s\n' "$previous" > "$SAVED"; fi
  handler "$ID"
  announce "$previous" "$ID"
}

uninstall() {
  previous=$(cat "$SAVED" 2>/dev/null || echo com.apple.TextEdit)
  if [ "$(handler || true)" = "$ID" ]; then handler "$previous"; fi
  "$LSREGISTER" -u "$APP" 2>/dev/null || true
  rm -rf "$APP" "$SAVED"
  echo "Markdown files open in $previous again."
}

linux_install() {
  command -v xdg-mime >/dev/null || { echo "Needs xdg-mime (xdg-utils)." >&2; exit 1; }
  herdr=$(command -v herdr-app || echo "$HOME/.local/bin/herdr-app")
  mkdir -p "$DESKTOP_APPS" "$INBOX" "$(dirname "$OPENER")"
  previous=$(xdg-mime query default text/markdown 2>/dev/null || true)
  for type in $LINUX_TYPES; do
    now=$(xdg-mime query default "$type" 2>/dev/null || true)
    if [ "$now" = "$ID.desktop" ]; then grep "^$type " "$SAVED" 2>/dev/null || true
    elif [ -n "$now" ]; then printf '%s %s\n' "$type" "$now"; fi
  done > "$SAVED.new"
  mv -f "$SAVED.new" "$SAVED"
  cat > "$OPENER" <<OPEN
#!/bin/sh
p=\$1
export HERDR_APP_HOME="$HOME_DIR"
if ! pgrep -x herdr-app >/dev/null; then
  case "\$p" in *.md|*.markdown) t=text/markdown ;; *) t=text/plain ;; esac
  back=\$(sed -n "s|^\$t ||p" "$SAVED" 2>/dev/null)
  [ -n "\$back" ] && command -v gtk-launch >/dev/null && exec gtk-launch "\${back%.desktop}" "\$p"
  exec "$herdr"
fi
$(hand_to_herdr)
command -v omarchy-launch-or-focus >/dev/null && exec omarchy-launch-or-focus herdr-app "$herdr"
exit 0
OPEN
  chmod +x "$OPENER"
  case "$OPENER" in *' '*) exec_line="\"$OPENER\" %f" ;; *) exec_line="$OPENER %f" ;; esac
  cat > "$DESKTOP_APPS/$ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Kanso Markdown
Exec=$exec_line
MimeType=text/markdown;text/x-markdown;text/plain;
NoDisplay=true
Terminal=false
DESKTOP
  refresh_desktop
  xdg-mime default "$ID.desktop" $LINUX_TYPES
  announce "$previous" "$ID.desktop"
}

linux_uninstall() {
  for type in $LINUX_TYPES; do
    back=$(sed -n "s|^$type ||p" "$SAVED" 2>/dev/null || true)
    if [ -n "$back" ] && [ "$(xdg-mime query default "$type" 2>/dev/null)" = "$ID.desktop" ]; then xdg-mime default "$back" "$type"; fi
  done
  rm -rf "$DESKTOP_APPS/$ID.desktop" "$(dirname "$OPENER")" "$HOME_DIR/data/kanso-markdown" "$SAVED"
  refresh_desktop
  now=$(xdg-mime query default text/markdown 2>/dev/null || true)
  echo "Markdown files open in ${now:-the system default} again."
}

status() { if [ "$(handler 2>/dev/null || true)" = "$ID" ]; then echo on; else echo off; fi; }

linux_status() {
  [ -x "$OPENER" ] || { echo off; return; }
  for type in $LINUX_TYPES; do [ "$(xdg-mime query default "$type" 2>/dev/null)" = "$ID.desktop" ] || { echo off; return; }; done
  echo on
}

case "$(uname):${1:-}" in
  Darwin:status) status ;;
  Linux:status) linux_status ;;
  Darwin:install) install ;;
  Darwin:uninstall) uninstall ;;
  Linux:install) linux_install ;;
  Linux:uninstall) linux_uninstall ;;
  Darwin:*|Linux:*) echo "Usage: sh $0 install | uninstall | status" >&2; exit 2 ;;
  *) echo "Kanso Markdown is for macOS and Linux." >&2; exit 1 ;;
esac
