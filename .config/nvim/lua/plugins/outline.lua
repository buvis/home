return {
  {
    "hedyhli/outline.nvim",
    keys = { { "<leader>o", "<cmd>Outline<cr>", desc = "Toggle Outline" } },
    cmd = "Outline",
    opts = {
      -- Configure specifically for markdown
      symbols = {
        filter = {
          default = { "String", exclude = true },
          markdown = { "String", "Property" },
        },
      },
    },
  },
}
