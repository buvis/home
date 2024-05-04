local treesitter = require("nvim-treesitter.configs")

treesitter.setup({
  autotag = { enable = true },
  ensure_installed = {
    "bash",
    "css",
    "dockerfile",
    "gitignore",
    "graphql",
    "html",
    "javascript",
    "json",
    "lua",
    "markdown",
    "markdown_inline",
    "python",
    "svelte",
    "tsx",
    "typescript",
    "vimdoc",
    "yaml",
  },
  highlight = { enable = true },
  indent = { enable = true },
})
