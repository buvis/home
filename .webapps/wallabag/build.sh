#!/usr/bin/env bash
# Build Wallabag app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Wallabag" --internal-urls ".*?" --icon wallabag.icns "https://app.wallabag.it/quickstart" ~/Applications/webapps
