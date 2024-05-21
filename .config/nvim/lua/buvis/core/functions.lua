-- This function will insert current time followed by dash and enter insert mode
function PasteCurrentDateTime()
  local currentTime = os.date("%d.%m.%Y %H:%M")
  vim.api.nvim_command("normal i" .. currentTime .. " - \n")
  vim.api.nvim_command("normal k")
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("A", true, true, true), "n", false)
end
