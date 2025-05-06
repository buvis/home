return {
  {
    "catppuccin/nvim",
    name = "catppuccin",
    priority = 1000,
    opts = {
      color_overrides = {
        latte = {
          rosewater = "#fdf7e8",
          flamingo = "#bc5819",
          pink = "#c44392",
          mauve = "#825dc0",
          red = "#d2212d",
          maroon = "#cc1729",
          peach = "#c25d1e",
          yellow = "#a78300",
          green = "#489100",
          teal = "#009c8f",
          sky = "#006dce",
          sapphire = "#00978a",
          blue = "#0072d4",
          lavender = "#8762c6",
          text = "#3a4d53",
          subtext1 = "#53676d",
          subtext0 = "#909995",
          overlay2 = "#002b36",
          overlay1 = "#839496",
          overlay0 = "#93a1a1",
          surface2 = "#eee8c5",
          surface1 = "#f2e5b0",
          surface0 = "#f4d797",
          base = "#fbf3db",
          mantle = "#ece3cc",
          crust = "#d5cdb6",
        },
      },
      dim_inactive = {
        enabled = true,
        shade = "dark",
        percentage = 0.55,
      },
      highlight_overrides = {
        -- Use :Inspect to find the highlight group
        latte = function(C)
          return {
            FlashLabel = { fg = C.base, bg = C.red, style = { "bold" } },
            LineNr = { fg = C.overlay0 },
            CursorLineNr = { fg = C.overlay2, bg = C.mantle },
            Comment = { fg = C.subtext0, style = { "italic" } },
            Keyword = { fg = C.maroon, style = { "bold" } },
            Statement = { fg = C.maroon, style = { "bold" } },
            Conditional = { fg = C.maroon, style = { "bold" } },
            Repeat = { fg = C.maroon, style = { "bold" } },
            Include = { fg = C.maroon, style = { "bold" } },
            ["@keyword.function"] = { fg = C.maroon, style = { "bold" } },
            ["@keyword.return"] = { fg = C.maroon, style = { "bold" } },
            ["@variable.member"] = { fg = C.mauve },
            ["@variable.parameter"] = { fg = C.peach },
            ["@property"] = { fg = C.text },
          }
        end,
      },
    },
  },
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "catppuccin-latte",
    },
  },
}
