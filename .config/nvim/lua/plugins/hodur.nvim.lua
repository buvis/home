return {
  "vodchella/hodur.nvim",
  config = function()
    require("hodur").setup({
      key = "<C-g>",
    })
  end,
}
