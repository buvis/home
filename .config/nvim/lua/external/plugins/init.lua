if vim.o.loadplugins then
  -- https://github.com/kwkarlwang/bufresize.nvim
  buvis.plugin.load('bufresize.nvim')
  require('external.plugins.bufresize')
  -- https://github.com/nvim-lualine/lualine.nvim
  buvis.plugin.load('lualine.nvim')
  require('external.plugins.lualine')
  -- https://github.com/Tsuzat/NeoSolarized.nvim
  buvis.plugin.load('NeoSolarized.nvim')
  require('external.plugins.NeoSolarized')
  -- https://github.com/nvim-tree/nvim-web-devicons
  buvis.plugin.load('nvim-web-devicons')
  require('external.plugins.nvim-web-devicons')
  -- https://github.com/nvim-lua/plenary.nvim
  buvis.plugin.load('plenary.nvim')
  -- https://github.com/wincent/replay
  buvis.plugin.load('replay')
  -- https://github.com/mrjones2014/smart-splits.nvim
  buvis.plugin.load('smart-splits.nvim')
  require('external.plugins.smart-splits')
  -- https://github.com/tpope/vim-commentary
  buvis.plugin.load('vim-commentary')
  -- https://github.com/folke/which-key.nvim
  buvis.plugin.load('which-key.nvim')
  require('external.plugins.which-key')

  -- Lazy loaded plugins (because they slow down the startup)
  require('external.plugins.lazy')
end

-- Automatic, language-dependent indentation, syntax coloring and other
-- functionality.
--
-- Must come *after* the `:packadd!` calls above otherwise the contents of
-- package "ftdetect" directories won't be evaluated.
vim.cmd('filetype indent plugin on')
vim.cmd('syntax on')
