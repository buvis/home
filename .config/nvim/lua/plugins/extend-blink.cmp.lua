return {
  { "giuxtaposition/blink-cmp-copilot", enabled = false },
  {
    "saghen/blink.cmp",
    dependencies = {
      "fang2hou/blink-copilot",
      {
        "mikavilpas/blink-ripgrep.nvim",
        version = "*",
      },
    },
    opts = {
      keymap = {
        preset = "enter",
        ["<S-Tab>"] = { "select_prev", "fallback" },
        ["<Tab>"] = { "select_next", "fallback" },
      },
      sources = {
        default = {
          "buffer",
          "ripgrep",
        },
        providers = {
          copilot = {
            module = "blink-copilot",
          },
          ripgrep = {
            module = "blink-ripgrep",
            name = "Ripgrep",
            ---@module "blink-ripgrep"
            ---@type blink-ripgrep.Options
            opts = {},
          },
        },
      },
    },
  },
}
