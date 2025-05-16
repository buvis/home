return {
  {
    -- dir = "~/git/src/github.com/buvis/padcosta.nvim/",
    "buvis/padcosta.nvim",
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
      build = ":TSUpdate",
    },
    opts = {},
    -- opts = { debug = true },
  },
}
