return {
  "mrjones2014/smart-splits.nvim",
  dependencies = { "kwkarlwang/bufresize.nvim" },
  config = function()
    local opts = {
      -- integration with bufresize.nvim
      resize_mode = {
        hooks = {
          on_leave = require("bufresize").register,
        },
      },
    }
    -- inside herdr: at a nvim edge, move to the herdr pane first, then the wezterm pane
    if vim.env.HERDR_PANE_ID then
      opts.multiplexer_integration = false
      opts.at_edge = function(ctx)
        local out = vim.system({ "herdr", "pane", "focus", "--direction", ctx.direction }):wait().stdout or ""
        if not out:find('"changed":true', 1, true) then
          local dir = ctx.direction:sub(1, 1):upper() .. ctx.direction:sub(2)
          vim.system({ "wezterm", "cli", "activate-pane-direction", dir })
        end
      end
    end
    require("smart-splits").setup(opts)
  end,
}
