local custom_solarized = require('lualine.themes.solarized_dark')

custom_solarized.normal.c.bg = '#002b36'

require('lualine').setup {
  options = { theme = custom_solarized },
}
