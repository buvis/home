return {
  "folke/which-key.nvim",
  opts = function(_, opts)
    -- Ensure opts.spec exists
    opts.spec = opts.spec or {}

    table.insert(opts.spec, {
      "<leader>a",
      group = "AI/Copilot",
      icon = { icon = require("lazyvim.config").icons.kinds.Copilot, color = "orange" },
    })

    table.insert(opts.spec, {
      "<leader>aa",
      function()
        return require("CopilotChat").toggle()
      end,
      desc = "Toggle (CopilotChat)",
      icon = { icon = "󰻞 ", color = "blue" },
      mode = { "n", "v" },
    })

    table.insert(opts.spec, {
      "<leader>ax",
      function()
        return require("CopilotChat").reset()
      end,
      desc = "Clear (CopilotChat)",
      icon = { icon = "󱐔 ", color = "red" },
      mode = { "n", "v" },
    })

    table.insert(opts.spec, {
      "<leader>aq",
      function()
        vim.ui.input({
          prompt = "Quick Chat: ",
        }, function(input)
          if input ~= "" then
            require("CopilotChat").ask(input)
          end
        end)
      end,
      desc = "Quick Chat (CopilotChat)",
      icon = { icon = "󱜹 ", color = "green" },
      mode = { "n", "v" },
    })

    table.insert(opts.spec, {
      "<leader>ap",
      function()
        require("CopilotChat").select_prompt()
      end,
      desc = "Prompt Actions (CopilotChat)",
      icon = { icon = "󱖬 ", color = "cyan" },
      mode = { "n", "v" },
    })

    return opts
  end,
}
