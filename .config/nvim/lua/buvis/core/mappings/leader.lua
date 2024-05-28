local keymap = vim.keymap
vim.g.mapleader = " "

keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })
keymap.set("n", "<leader>pd", ":lua PasteCurrentDateTime()<CR>", { desc = "Paste current date and time" })
