#!/usr/bin/env bash
# Build Inoreader app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Inoreader" --internal-urls ".*?" --icon inoreader.icns "http://inoreader.com/" ~/Applications/webapps
