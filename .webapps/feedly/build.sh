#!/usr/bin/env bash
# Build Feedly app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Feedly" --internal-urls ".*?" --icon feedly.icns "http://feedly.com/" ~/Applications/webapps
