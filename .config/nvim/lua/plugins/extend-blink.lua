return {
  { "giuxtaposition/blink-cmp-copilot", enabled = false },
  {
    "saghen/blink.cmp",
    dependencies = { "fang2hou/blink-copilot" },
    opts = {
      keymap = {
        ["<Tab>"] = { "select_and_accept" },
      },
      sources = {
        providers = {
          copilot = {
            module = "blink-copilot",
          },
        },
      },
    },
  },
}
