return {
  {
    "MeanderingProgrammer/render-markdown.nvim",
    dependencies = { "nvim-treesitter/nvim-treesitter", "echasnovski/mini.icons", "nvim-tree/nvim-web-devicons" },
    opts = {
      file_types = { "markdown" },
    },
    ft = { "markdown" },
  },
  {
    "mfussenegger/nvim-lint",
    opts = {
      linters_by_ft = {
        markdown = { "markdownlint-cli2" },
      },
      linters = {
        ["markdownlint-cli2"] = {
          args = { "--config", vim.fn.expand("~/.config/markdownlint/.markdownlint-cli2.yaml"), "--" },
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
