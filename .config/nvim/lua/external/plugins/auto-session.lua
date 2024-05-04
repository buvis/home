require('auto-session').setup({
  auto_restore_enabled = false,
  auto_session_suppress_dirs = { "~/", "~/Downloads" }
})

local keymap = vim.keymap

keymap.set("n", "<leader>wr", "<cmd>SessionRestore<CR>", { desc = "Restore session for cwd" })
keymap.set("n", "<leader>ws", "<cmd>SessionSave<CR>", { desc = "Save session for cwd" })
