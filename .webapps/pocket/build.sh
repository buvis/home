#!/usr/bin/env bash
# Build Pocket app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Pocket" --internal-urls ".*?" --icon pocket.icns "https://app.getpocket.com/" ~/Applications/webapps
