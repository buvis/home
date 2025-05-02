vim.api.nvim_create_autocmd("BufWritePre", {
  pattern = "*.py",
  callback = function()
    vim.lsp.buf.format({
      timeout_ms = 2000,
      filter = function(client)
        return client.name == "ruff" -- Exclude Pyright
      end,
    })
    vim.cmd("silent! !autopep8 --select=E301,E302,E303 --in-place %")
  end,
})
