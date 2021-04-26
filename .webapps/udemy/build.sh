#!/usr/bin/env bash
# Build Udemy app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "Udemy" --internal-urls ".*?" --icon udemy.icns "https://www.udemy.com/" ~/Applications/webapps
