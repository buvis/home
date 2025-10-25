return {
  "stevearc/conform.nvim",
  opts = function(_, opts)
    local util = require("conform.util")

    -- Ensure tables exist
    opts.formatters_by_ft = opts.formatters_by_ft or {}
    opts.formatters = opts.formatters or {}

    -- Filetype mappings
    opts.formatters_by_ft.python = { "ruff_fix", "ruff_format", "ruff_organize_imports" }
    opts.formatters_by_ft.markdown = { "rumdl" }

    -- Formatter definitions/overrides
    opts.formatters = vim.tbl_deep_extend("force", opts.formatters, {
      -- Ruff: fix -> format -> organize imports
      ruff_fix = {
        stdin = true,
        args = {
          "check",
          "--fix",
          "--force-exclude",
          "--exit-zero",
          "--no-cache",
          "--stdin-filename",
          "$FILENAME",
          "-",
        },
      },
      ruff_format = {
        stdin = true,
        args = { "format", "--stdin-filename", "$FILENAME", "-" },
      },

      -- rumdl: stdin formatting with quiet output; filename context and project-root cwd
      rumdl = {
        command = "rumdl",
        stdin = true,
        args = { "fmt", "--quiet", "--no-cache", "-" },
        cwd = util.root_file({ ".rumdl.toml", "rumdl.toml", "pyproject.toml", ".git" }),
        -- If rumdl signals remaining violations with exit 1, allow it as non-fatal:
        exit_codes = { 0, 1 },
      },
    })

    return opts
  end,
}
