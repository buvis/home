return {
  {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, opts)
      local install = require("nvim-treesitter.install")
      install.prefer_git = true
      install.compilers = { "clang", "gcc", "cl" }
      vim.list_extend(opts.ensure_installed, {
        "cmake",
        "css",
        "gitcommit",
        "gitignore",
        "go",
        "graphql",
        "http",
        "scss",
        "sql",
        "svelte",
        "vue",
      })
    end,
  },
}
