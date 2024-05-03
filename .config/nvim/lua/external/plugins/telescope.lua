require('telescope').setup({
  defaults = {
    path_display = { "smart" },
    mappings = {
      i = {
        ["<C-k>"] = require("telescope.actions").move_selection_previous,
        ["<C-j>"] = require("telescope.actions").move_selection_next,
      }
    }
  },
})

require("telescope").load_extension("zf-native")

local keymap = vim.keymap

keymap.set("n", "<leader>ff", "<cmd>Telescope find_files<CR>", { desc = "Fuzzy find files in cwd" })
keymap.set("n", "<leader>fg", "<cmd>Telescope live_grep<CR>", { desc = "Fuzzy find in files' content in cwd" })
