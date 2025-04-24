local keymap = vim.keymap
vim.g.mapleader = " "

keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })
keymap.set("n", "<leader>pd", ":lua PasteCurrentDateTime()<CR>", { desc = "Paste current date and time" })
keymap.set(
  "n",
  "<leader>s",
  [[:%s/\<<C-r><C-w>\>//gIc | nohlsearch<Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left><Left>]],
  { noremap = true, silent = false, desc = "Search and replace word under cursor with confirmation" }
)
