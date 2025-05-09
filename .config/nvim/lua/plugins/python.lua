return {
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        pyright = {
          settings = {
            pyright = {
              disableOrganizeImports = true,
            },
            python = {
              analysis = {
                diagnosticSeverityOverrides = {
                  reportUndefinedVariable = false,
                },
                typeCheckingMode = "basic",
                linting = false,
              },
            },
          },
        },
      },
    },
  },
  {
    "stevearc/conform.nvim",
    opts = {
      formatters_by_ft = {
        python = { "ruff_organize_imports", lsp_format = "first" },
      },
    },
  },
  {
    "roobert/f-string-toggle.nvim",
    keys = {
      {
        "<leader>rf",
        function()
          require("f-string-toggle").toggle_fstring()
        end,
        desc = "Toggle f-string",
      },
    },
    config = function()
      require("f-string-toggle").setup({
        key_binding = false,
      })
    end,
  },
}
