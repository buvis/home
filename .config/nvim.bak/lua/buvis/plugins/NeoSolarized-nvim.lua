return {
  {
    "Tsuzat/NeoSolarized.nvim",
    config = function()
      require("NeoSolarized").setup({
        style = "light",
        transparent = false,
      })
    vim.cmd([[colorscheme NeoSolarized]])
    end,
  },
}
