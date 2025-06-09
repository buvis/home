return {
  {
    "markgandolfo/lightswitch.nvim",
    dependencies = {
      "MunifTanjim/nui.nvim",
    },
    opts = {
      colors = {
        off = "#dc322f",
        on = "#859900",
      },
      toggles = {
        {
          name = "LSP",
          enable_cmd = ":LspStart<CR>",
          disable_cmd = ":LspStop<CR>",
          state = true,
        },
        {
          name = "Diagnostics",
          enable_cmd = "lua vim.diagnostic.enable()",
          disable_cmd = "lua vim.diagnostic.disable()",
          state = true,
        },
      },
    },
  },
}
