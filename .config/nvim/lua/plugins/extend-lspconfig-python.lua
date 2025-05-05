return {
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        pyright = {
          settings = {
            pyright = {
              disableOrganizeImports = true,
            },
            python = {
              analysis = {
                diagnosticSeverityOverrides = {
                  reportUndefinedVariable = false,
                },
                typeCheckingMode = "basic",
                linting = false,
              },
            },
          },
        },
      },
    },
  },
}
