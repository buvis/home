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
-- Customize whitespace characters
vim.opt.listchars = {
  nbsp = "⦸", -- CIRCLED REVERSE SOLIDUS (U+29B8, UTF-8: E2 A6 B8)
  extends = "»", -- RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK (U+00BB, UTF-8: C2 BB)
  precedes = "«", -- LEFT-POINTING DOUBLE ANGLE QUOTATION MARK (U+00AB, UTF-8: C2 AB)
  tab = "▷⋯", -- WHITE RIGHT-POINTING TRIANGLE (U+25B7, UTF-8: E2 96 B7) + MIDLINE HORIZONTAL ELLIPSIS (U+22EF, UTF-8: E2 8B AF)
  trail = "•", -- BULLET (U+2022, UTF-8: E2 80 A2)
}
-- Don't create shada files for root
if root then
  vim.opt.shada = ""
  vim.opt.shadafile = "NONE"
end
-- Store undofiles centrally
if root then
  vim.opt.undofile = false -- don't create root-owned files
else
  vim.opt.undodir = config .. "/.undo//" -- keep undo files out of the way
  vim.opt.undodir = vim.opt.undodir + "." -- fallback
  vim.opt.undofile = true -- actually use undo files
end
