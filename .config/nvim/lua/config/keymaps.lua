-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

vim.keymap.set("i", "jj", "<Esc>", { noremap = false, desc = "Exit INSERT mode by pressing" })
vim.keymap.set(
  "n",
  "Y",
  '"+y$',
  { noremap = true, silent = true, desc = "Yank from cursor to end of line to system clipboard" }
)
vim.keymap.set("n", "YY", '"+yy', { noremap = true, silent = true, desc = "Yank entire line to system clipboard" })
vim.keymap.set("n", "<Down>", function()
  vim.diagnostic.jump({ count = 1, float = true })
end, { noremap = true, silent = true, desc = "Jump to next error in Diagnostic" })
vim.keymap.set("n", "<Up>", function()
  vim.diagnostic.jump({ count = -1, float = true })
end, { noremap = true, silent = true, desc = "Jump to previous error in Diagnostic" })
vim.keymap.set("v", "Y", '"+y', { noremap = true, silent = true, desc = "Yank selection to system clipboard" })
