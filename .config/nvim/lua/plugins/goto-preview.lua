return {
  {
    "gbprod/yanky.nvim",
    keys = {
      { "gp", false },
      { "gP", false },
    },
  },
  {
    "rmagatti/goto-preview",
    dependencies = { "rmagatti/logger.nvim" },
    event = "BufEnter",
    config = true, -- necessary as per https://github.com/rmagatti/goto-preview/issues/88
    opts = {
      default_mappings = true,
    },
    keys = {
      { "gp", "", desc = "+Goto preview", mode = { "n" } },
    },
  },
}
