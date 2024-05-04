if vim.o.loadplugins then
  -- https://github.com/akinsho/bufferline.nvim
  buvis.plugin.load('bufferline.nvim')
  require('external.plugins.bufferline')
  -- https://github.com/kwkarlwang/bufresize.nvim
  buvis.plugin.load('bufresize.nvim')
  require('external.plugins.bufresize')
  -- https://github.com/stevearc/dressing.nvim
  buvis.plugin.load('dressing.nvim')
  require('external.plugins.dressing')
  -- https://github.com/lukas-reineke/indent-blankline.nvim
  buvis.plugin.load('indent-blankline.nvim')
  require('external.plugins.indent-blankline')
  -- https://github.com/nvim-lualine/lualine.nvim
  buvis.plugin.load('lualine.nvim')
  require('external.plugins.lualine')
  -- https://github.com/Tsuzat/NeoSolarized.nvim
  buvis.plugin.load('NeoSolarized.nvim')
  require('external.plugins.NeoSolarized')
  -- https://github.com/nvim-treesitter/nvim-treesitter
  buvis.plugin.load('nvim-treesitter')
  require('external.plugins.nvim-treesitter')
  -- https://github.com/windwp/nvim-ts-autotag
  buvis.plugin.load('nvim-ts-autotag')
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
  -- https://github.com/natecraddock/telescope-zf-native.nvim
  buvis.plugin.load('telescope-zf-native.nvim')
  -- https://github.com/nvim-telescope/telescope.nvim
  buvis.plugin.load('telescope.nvim')
  require('external.plugins.telescope')
  -- https://github.com/tpope/vim-commentary
  buvis.plugin.load('vim-commentary')
  -- https://github.com/szw/vim-maximizer
  buvis.plugin.load('vim-maximizer')
  require('external.plugins.vim-maximizer')
  -- https://github.com/folke/which-key.nvim
  buvis.plugin.load('which-key.nvim')
  require('external.plugins.which-key')

  -- Autocomplete functionality
  -- https://github.com/hrsh7th/nvim-cmp
  buvis.plugin.load('nvim-cmp')
  -- https://github.com/hrsh7th/cmp-buffer
  buvis.plugin.load('cmp-buffer')
  -- https://github.com/hrsh7th/cmp-path
  buvis.plugin.load('cmp-path')
  -- https://github.com/L3MON4D3/LuaSnip
  -- don't forget to run `make install_jsregexp` in plugin directory
  buvis.plugin.load('LuaSnip')
  -- https://github.com/saadparwaiz1/cmp_luasnip
  buvis.plugin.load('cmp_luasnip')
  -- https://github.com/rafamadriz/friendly-snippets
  buvis.plugin.load('friendly-snippets')
  -- https://github.com/onsails/lspkind.nvim
  buvis.plugin.load('lspkind.nvim')
  require('external.plugins.nvim-cmp')
  -- https://github.com/windwp/nvim-autopairs
  buvis.plugin.load('nvim-autopairs')
  require('external.plugins.nvim-autopairs')

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
