-- Lazy because it adds a slow BufEnter autocmd.
buvis.plugin.lazy('nvim-tree.lua', {
  afterload = function()
    require('nvim-tree').setup({
      view = {
        width = 35,
        relativenumber = true,
      },
      -- change folder arrow icons
      renderer = {
        indent_markers = {
          enable = true,
        },
        icons = {
          glyphs = {
            folder = {
              arrow_closed = "", -- arrow when folder is closed
              arrow_open = "", -- arrow when folder is open
            },
          },
        },
      },
      -- disable window_picker for
      -- explorer to work well with
      -- window splits
      actions = {
        open_file = {
          window_picker = {
            enable = false,
          },
        },
      },
      filters = {
        custom = { ".DS_Store" },
      },
      git = {
        ignore = false,
      },
    })
  end,
  commands = {
    'NvimTreeFindFile',
    'NvimTreeToggle',
    'NvimTreeOpen',
  },
  dependencies = 'nvim-tree/nvim-web-devicons',
  keymap = {
    { 'n', '<leader>ef', '<cmd>NvimTreeFindFileToggle<CR>', { silent = true, desc = "Toggle file explorer on current file" } },
    { 'n', '<leader>ee', '<cmd>NvimTreeToggle<CR>', { silent = true, desc = "Toggle file explorer" } },
    { 'n', '<leader>ec', '<cmd>NvimTreeCollapse<CR>', { silent = true , desc = "Collapse file explorer" } },
    { 'n', '<leader>er', '<cmd>NvimTreeRefresh<CR>', { silent = true , desc = "Refresh file explorer" } },
  },
})
