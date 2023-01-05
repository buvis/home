#!/usr/bin/env bash
# Build Reader app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Reader" --internal-urls ".*?" --icon reader.icns "https://read.readwise.io/new" ~/Applications/webapps
