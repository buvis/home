return {
  "neovim/nvim-lspconfig",
  opts = {
    servers = {
      harper_ls = {
        settings = {
          ["harper-ls"] = {
            userDictPath = vim.fn.expand("~/.config/harper-ls/dictionary.txt"),
            fileDictPath = vim.fn.expand("~/.config/harper-ls/file_dictionaries/"),
          },
        },
      },
    },
  },
}
