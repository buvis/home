local ok_status, NeoSolarized = pcall(require, "NeoSolarized")

if not ok_status then
  return
end

NeoSolarized.setup {
  style = "light", -- "dark" or "light"
  transparent = false, -- true/false; Enable this to disable setting the background color
}

vim.cmd 'colorscheme NeoSolarized'
