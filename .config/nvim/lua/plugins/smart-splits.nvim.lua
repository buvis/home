return {
  "mrjones2014/smart-splits.nvim",
  dependencies = { "kwkarlwang/bufresize.nvim" },
  config = function()
    -- integration with bufresize.nvim
    require("smart-splits").setup({
      resize_mode = {
        hooks = {
          on_leave = require("bufresize").register,
        },
      },
    })
  end,
}
