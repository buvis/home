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
    -- inside herdr-app: herdr-app owns ctrl-hjkl; its `nav` mod calls herdr_nav over
    -- this socket when the focused pane runs nvim. At a nvim edge, move the herdr-app pane.
    elseif vim.env.HC_TERMINAL_ID then
      opts.multiplexer_integration = false
      opts.at_edge = function(ctx)
        vim.system({ "herdr-app", "do", "pane.go", "--direction", ctx.direction })
      end
      local keys = { left = "<C-h>", down = "<C-j>", up = "<C-k>", right = "<C-l>" }
      _G.herdr_nav = function(dir)
        if vim.api.nvim_get_mode().mode == "n" then
          require("smart-splits")["move_cursor_" .. dir]()
        else
          -- other modes keep the key's own meaning (insert: ctrl-h deletes)
          vim.api.nvim_input(keys[dir])
        end
        return ""
      end
      local dir = vim.fn.expand("~/.cache/nvim")
      vim.fn.mkdir(dir, "p")
      local sock = dir .. "/herdr-" .. vim.env.HC_TERMINAL_ID .. ".sock"
      if not pcall(vim.fn.serverstart, sock) then
        os.remove(sock) -- stale socket from a crashed nvim
        pcall(vim.fn.serverstart, sock)
      end
    end
    require("smart-splits").setup(opts)
  end,
}
