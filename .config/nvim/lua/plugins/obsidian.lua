return {
  "obsidian-nvim/obsidian.nvim",
  version = "*",
  lazy = true,
  ft = "markdown",
  dependencies = {
    "nvim-lua/plenary.nvim",
  },
  opts = {
    frontmatter = {
      disabled = true,
    },
    workspaces = {
      {
        name = "bim",
        path = "~/bim/",
      },
    },
  },
}
