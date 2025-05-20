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

-- Disable Copilot in private folder
local home = vim.fn.expand("~")
vim.api.nvim_create_autocmd({ "BufRead", "BufNewFile" }, {
  pattern = home .. "/bim/*",
  callback = function()
    vim.cmd("Copilot disable")
  end,
  desc = "Disable Copilot in private folder",
})

--[[ Open plugin repos with gx ]]
vim.api.nvim_create_autocmd("BufReadPost", {
  group = vim.api.nvim_create_augroup("GxWithPlugins", { clear = true }),
  callback = function()
    local cwd = vim.fn.getcwd()
    local config_dir = vim.fn.stdpath("config")

    if cwd == config_dir or cwd:sub(1, #config_dir + 1) == config_dir .. "/" then
      vim.keymap.set("n", "gx", function()
        local file = vim.fn.expand("<cfile>") --[[@as string]]

        -- First try the default behavior
        -- see https://github.com/neovim/neovim/blob/b0f9228179bf781eec76d1aaf346b56a7e64cd5d/runtime/lua/vim/_defaults.lua#L101
        -- for recent changes in `vim.ui.open`
        local cmd, err = vim.ui.open(file)
        local rv = cmd and cmd:wait(1000) or nil

        if cmd and rv and rv.code ~= 0 then
          err = ("vim.ui.open: command %s (%d): %s"):format(
            (rv.code == 124 and "timeout" or "failed"),
            rv.code,
            vim.inspect(cmd.cmd)
          )
        end

        if not err then
          return
        end

        -- Consider anything that looks like string/string a GitHub link.
        local link = file:match("%w[%w%-]+/[%w%-%._]+")

        if link then
          vim.ui.open("https://www.github.com/" .. link)
          err = nil
        end

        -- Else show the error

        if err then
          vim.notify(err, vim.log.levels.ERROR)
        end
      end, { desc = "Open filepath or URI under cursor" })
    end
  end,
  desc = "Make `gx` open repos in default browser",
})
