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
    local bufnr = vim.api.nvim_get_current_buf()

    -- Use Neovim's built-in code action handler for Ruff compatibility
    vim.lsp.buf.code_action({
      context = {
        only = { "source.organizeImports", "source.fixAll.ruff" },
        diagnostics = {},
      },
      filter = function(action)
        return action.title:lower():find("import") ~= nil
      end,
      apply = true,
      bufnr = bufnr,
    })
  end,
})
