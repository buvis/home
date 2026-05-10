return {
  "yarospace/dev-tools.nvim",
  dependencies = {
    "nvim-treesitter/nvim-treesitter",
    {
      "folke/snacks.nvim",
      opts = {
        picker = { enabled = true },
        terminal = { enabled = true },
      },
    },
    {
      "ThePrimeagen/refactoring.nvim",
      dependencies = { "lewis6991/async.nvim" },
    },
  },
  opts = {
    filetypes = {
      include = {},
      exclude = {},
    },
    actions = {},
  },
  event = {
    "BufEnter",
    "BufReadPre",
    "BufNewFile",
  },
}
