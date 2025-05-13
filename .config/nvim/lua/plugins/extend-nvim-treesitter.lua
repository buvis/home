return {
  {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, opts)
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
