return {
  {
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    dependencies = {
      "mason-org/mason.nvim",
      "mason-org/mason-lspconfig.nvim",
      "jay-babu/mason-nvim-dap.nvim",
      "jay-babu/mason-null-ls.nvim",
    },
    event = "VeryLazy",
    opts = {
      -- unified list: mix LSPs, DAPs, and CLI tools
      ensure_installed = {
        -- LSPs (Mason or lspconfig names both work with integrations)
        "ansiblels",
        "bashls",
        "docker_compose_language_service",
        "dockerls",
        "harper_ls",
        "helm_ls",
        "jsonls",
        "lua_ls",
        "marksman",
        "pyright",
        -- ruff is LSP and formatter but must be listed once: duplicate entries
        -- hang MasonToolsUpdateSync (second entry's on_close never fires while
        -- the first is still installing, so the completion count never adds up)
        "ruff",
        "svelte",
        "taplo",
        "terraformls",
        "vtsls",
        "yamlls",
        -- DAPs
        "debugpy",
        -- Formatters/Linters
        "ast_grep",
        "black",
        "rumdl",
        "shellcheck",
        "shfmt",
        "stylua",
      },
      run_on_start = true,
      start_delay = 3000,
      debounce_hours = 5,
      auto_update = true,
      integrations = {
        ["mason-lspconfig"] = true,
        ["mason-nvim-dap"] = true,
        ["mason-null-ls"] = true,
      },
    },
    config = function(_, opts)
      -- Mason is configured by LazyVim; just start the tool installer
      require("mason-tool-installer").setup(opts)
    end,
  },

  -- Neutralize LazyVim’s own Mason ensure_installed to avoid duplication
  {
    "mason-org/mason.nvim",
    opts = function(_, opts)
      opts.ensure_installed = {} -- let mason-tool-installer be the single source of truth
    end,
  },
}
