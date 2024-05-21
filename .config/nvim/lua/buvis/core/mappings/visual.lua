-- Replace highlighted text
-- https://stackoverflow.com/a/676619
vim.cmd('vnoremap <C-r> "hy:%s/<C-r>h//gc<left><left><left>')

-- Copy selection to system clipboard
vim.cmd('vnoremap Y "*y')
