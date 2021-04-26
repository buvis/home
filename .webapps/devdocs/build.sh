#!/usr/bin/env bash
# Build DevDocs app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "DevDocs" --internal-urls ".*?" --icon devdocs.icns "https://devdocs.io" ~/Applications/webapps
