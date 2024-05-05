return {
  "lukas-reineke/indent-blankline.nvim",
  event = { "BufReadPre", "BufNewFile" },
  config = function()
    local hooks = require("ibl.hooks")
    hooks.register(hooks.type.HIGHLIGHT_SETUP, function()
      vim.api.nvim_set_hl(0, "CurrentScope", { fg = "#cb4b16", bg = "#eee8d5" })
    end)

    require("ibl").setup({
      indent = { char = "┊" },
      scope = { highlight = 'CurrentScope' },
    })
  end,
}
