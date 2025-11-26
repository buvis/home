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
vim.keymap.set("n", "<BS>", ":edit #<cr>", { silent = true })

-- [START] Smart Splits
-- remove LazyVim's mappings
vim.keymap.del("n", "<C-h>")
vim.keymap.del("n", "<C-j>")
vim.keymap.del("n", "<C-k>")
vim.keymap.del("n", "<C-l>")
-- resizing splits
-- these keymaps will also accept a range,
-- for example `10<A-h>` will `resize_left` by `(10 * config.default_amount)`
vim.keymap.set("n", "<A-h>", require("smart-splits").resize_left)
vim.keymap.set("n", "<A-j>", require("smart-splits").resize_down)
vim.keymap.set("n", "<A-k>", require("smart-splits").resize_up)
vim.keymap.set("n", "<A-l>", require("smart-splits").resize_right)
-- moving between splits
vim.keymap.set("n", "<C-h>", require("smart-splits").move_cursor_left)
vim.keymap.set("n", "<C-j>", require("smart-splits").move_cursor_down)
vim.keymap.set("n", "<C-k>", require("smart-splits").move_cursor_up)
vim.keymap.set("n", "<C-l>", require("smart-splits").move_cursor_right)
vim.keymap.set("n", "<C-\\>", require("smart-splits").move_cursor_previous)
-- [END] Smart Splits
