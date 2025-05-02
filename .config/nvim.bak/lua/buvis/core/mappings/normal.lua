local keymap = vim.keymap

-- tabs management
keymap.set("n", "<C-t>c", "<cmd>tabnew<CR>", { desc = "Create new tab" })
keymap.set("n", "<C-t>h", "<cmd>tabp<CR>", { desc = "Go to previous tab" })
keymap.set("n", "<C-t>l", "<cmd>tabn<CR>", { desc = "Go to next tab" })
keymap.set("n", "<C-t>q", "<cmd>tabclose<CR>", { desc = "Close tab" })
keymap.set("n", "<C-t>t", "<cmd>tabnew %<CR>", { desc = "Open current buffer in new tab" })
