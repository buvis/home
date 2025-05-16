-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
--
-- Add any additional autocmds here
-- with `vim.api.nvim_create_autocmd`
--
-- Or remove existing autocmds by their group name (which is prefixed with `lazyvim_` for the defaults)
-- e.g. vim.api.nvim_del_augroup_by_name("lazyvim_wrap_spell")

-- [BEGIN] Inactive window indication
-- Handle cursorline for insert mode
vim.api.nvim_create_autocmd({ "InsertLeave", "WinEnter" }, {
  callback = function()
    if vim.w.auto_cursorline then
      vim.wo.cursorline = true
      vim.w.auto_cursorline = nil
    end
  end,
})

vim.api.nvim_create_autocmd({ "InsertEnter", "WinLeave" }, {
  callback = function()
    if vim.wo.cursorline then
      vim.wo.cursorline = false
      vim.w.auto_cursorline = true
    end
  end,
})

-- Handle line numbers exclusively for window focus changes
vim.api.nvim_create_autocmd("WinEnter", {
  callback = function()
    if vim.w.auto_linenumbers then
      vim.wo.number = vim.w.auto_linenumbers.number
      vim.wo.relativenumber = vim.w.auto_linenumbers.relativenumber
      vim.w.auto_linenumbers = nil
    end
  end,
})

vim.api.nvim_create_autocmd("WinLeave", {
  callback = function()
    local current = {
      number = vim.wo.number,
      relativenumber = vim.wo.relativenumber,
    }

    if current.number or current.relativenumber then
      vim.w.auto_linenumbers = current
      vim.wo.number = false
      vim.wo.relativenumber = false
    end
  end,
})
-- [END] Inactive window indication

-- Use normal J if split/join not supported by treesj
local langs = require("treesj.langs")["presets"]

vim.api.nvim_create_autocmd({ "FileType" }, {
  pattern = "*",
  callback = function()
    local opts = { buffer = true }

    if langs[vim.bo.filetype] then
      vim.keymap.set("n", "J", "<Cmd>TSJToggle<CR>", opts)
    else
      vim.keymap.set("n", "J", function()
        vim.cmd("normal! J")
      end, opts)
    end
  end,
})
