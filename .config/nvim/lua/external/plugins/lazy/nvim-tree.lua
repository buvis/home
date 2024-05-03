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
  dependencies = 'nvim-tree/nvim-web-devicons',
  keymap = {
    { 'n', '<LocalLeader>f', ':NvimTreeFindFile<CR>', { silent = true } },
    { 'n', '<LocalLeader>t', ':NvimTreeToggle<CR>', { silent = true } },
  },
})
