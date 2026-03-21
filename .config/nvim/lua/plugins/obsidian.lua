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
    legacy_commands = false,
    workspaces = {
      {
        name = "bim",
        path = "~/bim/",
      },
    },
  },
}
