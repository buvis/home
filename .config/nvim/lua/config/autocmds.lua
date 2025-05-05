-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
--
-- Add any additional autocmds here
-- with `vim.api.nvim_create_autocmd`
--
-- Or remove existing autocmds by their group name (which is prefixed with `lazyvim_` for the defaults)
-- e.g. vim.api.nvim_del_augroup_by_name("lazyvim_wrap_spell")

-- Disable cursorline highlight in inactive windows
vim.api.nvim_create_autocmd({ "InsertLeave", "WinEnter" }, {
  callback = function()
    if vim.w.auto_cursorline then
      vim.wo.cursorline = true
      vim.w.auto_cursorline = nil
    end

    if vim.w.auto_linenumbers then
      vim.wo.number = vim.w.auto_linenumbers.number
      vim.wo.relativenumber = vim.w.auto_linenumbers.relativenumber
      vim.w.auto_linenumbers = nil
    end
  end,
})
vim.api.nvim_create_autocmd({ "InsertEnter", "WinLeave" }, {
  callback = function()
    if vim.wo.cursorline then
      vim.wo.cursorline = false
      vim.w.auto_cursorline = true
    end

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
