#!/usr/bin/env bash
# Build YNAB app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Habitica" --internal-urls ".*?" --icon habitica.icns "https://habitica.com/" ~/Applications/webapps
