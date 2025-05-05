return {
  "sunjon/Shade.nvim",
  config = function()
    require("shade").setup({
      overlay_opacity = 42, -- 0 to 100, default is 50
      opacity_step = 1, -- step for changing opacity with keybinds
      keys = {
        brightness_up = "<C-Up>",
        brightness_down = "<C-Down>",
      },
    })
  end,
  event = "VeryLazy", -- loads on startup
}
