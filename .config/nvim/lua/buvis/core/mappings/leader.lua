local keymap = vim.keymap
vim.g.mapleader = " "

keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })
