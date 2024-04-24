local wezterm = require("wezterm")

local config = {}

config.audible_bell = "Disabled"
config.check_for_updates = false
config.color_scheme = "Builtin Solarized Dark"
config.inactive_pane_hsb = {
  hue = 0.45,
  saturation = 0.75,
  brightness = 0.44,
}
if wezterm.target_triple == 'x86_64-pc-windows-msvc' then
  config.font_size = 10.5
else
  config.font_size = 12
end
config.launch_menu = {}

if wezterm.target_triple == 'x86_64-pc-windows-msvc' then
  config.leader = { key="\\" }
else
  config.leader = { key="§" }
end

config.disable_default_key_bindings = true
config.keys = {
  { key = "1", mods = "LEADER",       action=wezterm.action{ActivateTab=0}},
  { key = "2", mods = "LEADER",       action=wezterm.action{ActivateTab=1}},
  { key = "3", mods = "LEADER",       action=wezterm.action{ActivateTab=2}},
  { key = "4", mods = "LEADER",       action=wezterm.action{ActivateTab=3}},
  { key = "5", mods = "LEADER",       action=wezterm.action{ActivateTab=4}},
  { key = "6", mods = "LEADER",       action=wezterm.action{ActivateTab=5}},
  { key = "7", mods = "LEADER",       action=wezterm.action{ActivateTab=6}},
  { key = "8", mods = "LEADER",       action=wezterm.action{ActivateTab=7}},
  { key = "9", mods = "LEADER",       action=wezterm.action{ActivateTab=8}},
  { key = "c", mods = "LEADER",       action=wezterm.action{SpawnTab="CurrentPaneDomain"}},
  { key = "s", mods = "LEADER",       action=wezterm.action{SplitVertical={domain="CurrentPaneDomain"}}},
  { key = "v", mods = "LEADER",       action=wezterm.action{SplitHorizontal={domain="CurrentPaneDomain"}}},
  { key = "w", mods = "LEADER",       action=wezterm.action{CloseCurrentTab={confirm=true}}},
  { key = "x", mods = "LEADER",       action=wezterm.action{CloseCurrentPane={confirm=true}}},
  { key = "z", mods = "LEADER",       action="TogglePaneZoomState" },
  { key = "h", mods = "CTRL",         action=wezterm.action{ActivatePaneDirection="Left"}},
  { key = "j", mods = "CTRL",         action=wezterm.action{ActivatePaneDirection="Down"}},
  { key = "k", mods = "CTRL",         action=wezterm.action{ActivatePaneDirection="Up"}},
  { key = "l", mods = "CTRL",         action=wezterm.action{ActivatePaneDirection="Right"}},
  { key = "H", mods = "CTRL|SHIFT",   action=wezterm.action{AdjustPaneSize={"Left", 5}}},
  { key = "J", mods = "CTRL|SHIFT",   action=wezterm.action{AdjustPaneSize={"Down", 5}}},
  { key = "K", mods = "CTRL|SHIFT",   action=wezterm.action{AdjustPaneSize={"Up", 5}}},
  { key = "L", mods = "CTRL|SHIFT",   action=wezterm.action{AdjustPaneSize={"Right", 5}}},
  { key = "v", mods = "CTRL|SHIFT",   action=wezterm.action.PasteFrom 'Clipboard'},
  { key = "c", mods = "CTRL|SHIFT",   action=wezterm.action.CopyTo 'Clipboard'},
}
config.set_environment_variables = {}

if wezterm.target_triple == 'aarch64-apple-darwin' then
  config.set_environment_variables.PATH = '/opt/homebrew/bin:' .. os.getenv 'PATH'
end

config.set_environment_variables.PATH = os.getenv 'HOME' .. '/scripts/bin:' .. config.set_environment_variables.PATH
config.set_environment_variables.EDITOR = 'nvim'

config.default_prog = {'nu'}

return config
