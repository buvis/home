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
                  reportUnusedImport = "warning",
                  reportMissingImports = true,
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
  {
    "danymat/neogen",
    opts = {
      enabled = true,
      languages = {
        python = {
          template = {
            annotation_convention = "reST",
          },
        },
      },
    },
    keys = {
      {
        "<leader>cgd",
        function()
          require("neogen").generate()
        end,
        desc = "Generate Docstring",
      },
    },
  },
  {
    "hrsh7th/nvim-cmp",
    dependencies = {
      "hrsh7th/cmp-nvim-lsp",
      "hrsh7th/cmp-buffer",
      "hrsh7th/cmp-path",
      "hrsh7th/cmp-cmdline",
      "hrsh7th/cmp-nvim-lua",
      "onsails/lspkind.nvim",
      {
        "L3MON4D3/LuaSnip",
        dependencies = { "rafamadriz/friendly-snippets" },
      },
      "saadparwaiz1/cmp_luasnip",
    },
    opts = function(_, opts)
      local cmp = require("cmp")
      -- Improved completion setup for Python
      opts.sources = cmp.config.sources({
        { name = "nvim_lsp", priority = 1000 },
        { name = "luasnip", priority = 750 },
        { name = "buffer", priority = 500 },
        { name = "path", priority = 250 },
      })

      -- Add Python-specific snippets
      require("luasnip.loaders.from_vscode").lazy_load({
        paths = { "./snippets" },
      })

      return opts
    end,
  },
}
