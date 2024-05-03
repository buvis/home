if vim.loader then
  vim.loader.enable()
end

require('buvis')

-------------------------------------------------------------------------------
-- Plugins {{{1 ---------------------------------------------------------------
-------------------------------------------------------------------------------
if vim.o.loadplugins then
  -- https://github.com/kwkarlwang/bufresize.nvim
  buvis.plugin.load('bufresize.nvim')
  -- https://github.com/nvim-lualine/lualine.nvim
  buvis.plugin.load('lualine.nvim')
  -- https://github.com/Tsuzat/NeoSolarized.nvim
  buvis.plugin.load('NeoSolarized.nvim')
  -- https://github.com/nvim-tree/nvim-web-devicons
  buvis.plugin.load('nvim-web-devicons')
  -- https://github.com/wincent/replay
  buvis.plugin.load('replay')
  -- https://github.com/mrjones2014/smart-splits.nvim
  buvis.plugin.load('smart-splits.nvim')
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

-------------------------------------------------------------------------------
-- Footer {{{1 ----------------------------------------------------------------
-------------------------------------------------------------------------------

--[[

After this file is sourced, plugin code will be evaluated (eg.
~/.config/nvim/plugin/* and so on ). See ~/.config/nvim/after for files
evaluated after that.  See `:scriptnames` for a list of all scripts, in
evaluation order.

Launch Neovim with `nvim --startuptime nvim.log` for profiling info.

To see all leader mappings, including those from plugins:

    nvim -c 'map <Leader>'
    nvim -c 'map <LocalLeader>'

--]]

-------------------------------------------------------------------------------
-- Modeline {{{1 --------------------------------------------------------------
-------------------------------------------------------------------------------

-- vim: foldmethod=marker
