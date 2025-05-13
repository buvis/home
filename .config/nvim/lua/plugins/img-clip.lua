return {
  "HakonHarnes/img-clip.nvim",
  event = "VeryLazy",
  opts = {
    default = {
      dir_path = "~/bim/reference/30-resources/img-pasted/",
    },
  },
  keys = {
    { "<leader>i", "<cmd>PasteImage<cr>", desc = "Insert link to image from system clipboard" },
  },
}
