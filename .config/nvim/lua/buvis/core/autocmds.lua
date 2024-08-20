-- Set root directory to project

-- Array of file names indicating root directory. Modify to your liking.
local root_names = { ".git", "Makefile" }

-- Cache to use for speed up (at cost of possibly outdated results)
local root_cache = {}

local set_root = function()
  -- Get directory path to start search from
  local path = vim.api.nvim_buf_get_name(0)
  if path == "" then
    return
  end
  path = vim.fs.dirname(path)

  -- Try cache and resort to searching upward for root directory
  local root = root_cache[path]
  if root == nil then
    local root_file = vim.fs.find(root_names, { path = path, upward = true })[1]
    if root_file == nil then
      return
    end
    root = vim.fs.dirname(root_file)
    root_cache[path] = root
  end

  -- Set current directory
  vim.fn.chdir(root)
end

local root_augroup = vim.api.nvim_create_augroup("MyAutoRoot", {})
vim.api.nvim_create_autocmd("BufEnter", { group = root_augroup, callback = set_root })

-- Sort imports on save
vim.api.nvim_create_autocmd("BufWritePre", {
  callback = function()
    local params = vim.lsp.util.make_range_params()
    params.context = { diagnostics = vim.lsp.diagnostic.get_line_diagnostics() }

    local clients = vim.lsp.get_clients({ bufnr = 0, method = "textDocument/codeAction" })
    if #clients == 0 then
      return
    end

    local results = vim.lsp.buf_request_sync(0, "textDocument/codeAction", params)
    if not results then
      return
    end

    for _, result in pairs(results) do
      for _, action in pairs(result.result or {}) do
        if action.kind == "source.organizeImports" then
          vim.lsp.buf.code_action({ context = { only = { "source.organizeImports" } }, apply = true })
          vim.wait(100)
          break
        end
      end
    end
  end,
})
