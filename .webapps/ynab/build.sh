#!/usr/bin/env bash
# Build YNAB app using nativefier (https://github.com/nativefier/nativefier)
nativefier --internal-urls ".*?" --icon ynab-logo.icns "https://app.youneedabudget.com/"
