local custom_solarized = require('lualine.themes.solarized_dark')

custom_solarized.normal.c.bg = '#002b36'

require('lualine').setup({
  options = { theme = custom_solarized },
  sections = {
    lualine_c = {
      {
        'filename',
        file_status = true, -- displays file status (readonly status, modified status)
        path = 1 -- display path relative to project's root
      }
    }
  },
})
