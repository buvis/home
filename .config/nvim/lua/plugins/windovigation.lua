return {
  {
    "volskaya/windovigation.nvim",
    lazy = false,
    opts = {},
  },
  {
    "folke/persistence.nvim",
    event = "BufReadPre",
    opts = {
      pre_save = function()
        require("windovigation.actions").persist_state()
      end,
    },
  },
}
