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

-- Add blank line before control statements
local api = vim.api

api.nvim_create_autocmd({ "BufWritePre" }, {
	pattern = "*",
	callback = function()
		local buf = api.nvim_get_current_buf()
		local parser = vim.treesitter.get_parser(buf)
		if not parser then
			return
		end

		-- Language-specific fallback queries
		-- Run :InspectTree or :TSPlayground on a code snippet to see valid node types for your language.
		local queries = {
			javascript = [[  
        (if_statement) @if  
        (for_statement) @for  
        (while_statement) @while  
        (try_statement) @try  
        (switch_statement) @switch  
        (return_statement) @return  
      ]],
			python = [[  
        (if_statement) @if  
        (for_statement) @for  
        (while_statement) @while  
        (try_statement) @try  
        (return_statement) @return  
      ]],
			rust = [[  
        (if_expression) @if  
        (for_expression) @for  
        (while_expression) @while  
        (match_expression) @match  
        (return_expression) @return  
      ]],
			-- Default fallback (minimal)
			default = [[  
        (if_statement) @if  
        (for_statement) @for  
        (while_statement) @while  
      ]],
		}

		-- Get the language name (e.g., "python", "JavaScript")
		local lang = parser:lang()
		local query_str = queries[lang] or queries.default

		-- Safely parse the query (skip if invalid)
		local ok, query = pcall(vim.treesitter.query.parse, lang, query_str)
		if not ok then
			return
		end

		-- Rest of the logic (same as before)
		local root = parser:parse()[1]:root()
		local changes = {}

		for _, node in query:iter_captures(root, buf, 0, -1) do
			local start_line = node:start()
			local prev_line = api.nvim_buf_get_lines(buf, start_line - 1, start_line, false)[1]
			if prev_line and prev_line:match("^%s*$") == nil then
				table.insert(changes, start_line)
			end
		end

		-- Apply changes in reverse
		for i = #changes, 1, -1 do
			api.nvim_buf_set_lines(buf, changes[i], changes[i], false, { "" })
		end
	end,
})
