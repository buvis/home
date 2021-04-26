#!/usr/bin/env bash
# Build OurGroceries app using nativefier (https://github.com/nativefier/nativefier)
nativefier --name "OurGroceries" --internal-urls ".*?" --icon ourgroceries.icns "https://www.ourgroceries.com/your-lists/list/EUZD60UyHBqDbOK1Z6YaeQ" ~/Applications/webapps
