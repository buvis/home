return {
  {
    "MeanderingProgrammer/render-markdown.nvim",
    dependencies = { "nvim-treesitter/nvim-treesitter", "nvim-mini/mini.icons", "nvim-tree/nvim-web-devicons" },
    opts = {
      file_types = { "markdown" },
    },
    ft = { "markdown" },
  },
  {
    "mfussenegger/nvim-lint",
    opts = {
      linters_by_ft = {
        markdown = { "rumdl" },
      },
      linters = {
        ["rumdl"] = {
          cmd = "rumdl",
          stdin = false, -- inconsistent if set to true
          args = { "check", "--no-cache" },
          stream = "stdout",
          ignore_exitcode = true,
          env = nil,
          parser = require("lint.parser").from_pattern("([^:]+):(%d+):(%d+): %[([^%]]+)%] (.+)", {
            "file",
            "lnum",
            "col",
            "code",
            "message",
          }, {
            -- severity mapping -> useful if integrated with note taking tools eg markdown-oxide
          }, {
            source = "rumdl",
            severity = vim.diagnostic.severity.WARN,
          }),
        },
      },
    },
  },
  {
    "L3MON4D3/LuaSnip",
    dependencies = {
      "rafamadriz/friendly-snippets",
    },
    config = function()
      require("luasnip.loaders.from_vscode").lazy_load()
    end,
  },
  {
    "neovim/nvim-lspconfig",
    opts = function()
      -- Set markdown-specific options when entering a markdown buffer
      vim.api.nvim_create_autocmd("FileType", {
        pattern = "markdown",
        callback = function()
          -- Better word navigation for markdown
          vim.opt_local.wrap = true
          vim.opt_local.linebreak = true
          -- Show markdown syntax elements
          vim.opt_local.conceallevel = 2
          -- Enable spell checking
          vim.opt_local.spell = true
        end,
      })
    end,
  },
}
