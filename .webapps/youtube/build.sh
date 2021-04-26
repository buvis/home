#!/usr/bin/env bash
# Build Youtube app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Youtube" --user-agent "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:70.0) Gecko/20100101 Firefox/70.0" --internal-urls ".*?" --icon youtube.icns "https://youtube.com/" ~/Applications/webapps
