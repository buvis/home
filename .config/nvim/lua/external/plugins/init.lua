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
  -- https://github.com/wincent/replay
  buvis.plugin.load('replay')
  -- https://github.com/mrjones2014/smart-splits.nvim
  buvis.plugin.load('smart-splits.nvim')
  require('external.plugins.smart-splits')
  -- https://github.com/tpope/vim-commentary
  buvis.plugin.load('vim-commentary')

  -- Lazy because it adds a slow BufEnter autocmd.
  buvis.plugin.lazy('nvim-tree.lua', {
    afterload = function()
      require('nvim-tree').setup()
    end,
    commands = {
      'NvimTreeFindFile',
      'NvimTreeToggle',
      'NvimTreeOpen',
   },
    keymap = {
      { 'n', '<LocalLeader>f', ':NvimTreeFindFile<CR>', { silent = true } },
      { 'n', '<LocalLeader>t', ':NvimTreeToggle<CR>', { silent = true } },
    },
  })
end

-- Automatic, language-dependent indentation, syntax coloring and other
-- functionality.
--
-- Must come *after* the `:packadd!` calls above otherwise the contents of
-- package "ftdetect" directories won't be evaluated.
vim.cmd('filetype indent plugin on')
vim.cmd('syntax on')

