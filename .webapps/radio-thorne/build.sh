#!/usr/bin/env bash
# Build Mopidy-Iris app for thorne using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "radio-thorne" --internal-urls ".*?" --icon radio-thorne.icns "http://10.7.0.107:6680/iris/" ~/Applications/webapps
