-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
-- Add any additional options here

local home = vim.env.HOME
local config = home .. "/.config/nvim"
local root = vim.env.USER == "root"

-- Set light theme
vim.opt.background = "light"
-- Don't use system clipboard for yank, delete, and paste operations
vim.opt.clipboard = ""
-- Store undofiles centrally
if root then
  vim.opt.undofile = false -- don't create root-owned files
else
  vim.opt.undodir = config .. "/.undo//" -- keep undo files out of the way
  vim.opt.undodir = vim.opt.undodir + "." -- fallback
  vim.opt.undofile = true -- actually use undo files
end
-- Show file name in winbar
vim.opt.winbar = "%=%m %f"
