local wezterm = require("wezterm")
local act = wezterm.action

local config = {}

config.audible_bell = "Disabled"
config.check_for_updates = false
config.color_scheme = "Builtin Solarized Dark"
config.inactive_pane_hsb = {
  hue = 0.75,
  saturation = 0.75,
  brightness = 0.65,
}
config.font = wezterm.font 'MesloLGS NF'
if wezterm.target_triple == 'x86_64-pc-windows-msvc' then
  config.font_size = 10.5
else
  config.font_size = 11
end
config.launch_menu = {}

config.leader = { key="a", mods = "CTRL" }

config.disable_default_key_bindings = true
config.keys = {
  { key = "1", mods = "LEADER",       action=act{ActivateTab=0}},
  { key = "2", mods = "LEADER",       action=act{ActivateTab=1}},
  { key = "3", mods = "LEADER",       action=act{ActivateTab=2}},
  { key = "4", mods = "LEADER",       action=act{ActivateTab=3}},
  { key = "5", mods = "LEADER",       action=act{ActivateTab=4}},
  { key = "6", mods = "LEADER",       action=act{ActivateTab=5}},
  { key = "7", mods = "LEADER",       action=act{ActivateTab=6}},
  { key = "8", mods = "LEADER",       action=act{ActivateTab=7}},
  { key = "9", mods = "LEADER",       action=act{ActivateTab=8}},
  { key = "c", mods = "LEADER",       action=act{SpawnTab="CurrentPaneDomain"}},
  { key = "h", mods = "LEADER",       action=act{ActivatePaneDirection="Left"}},
  { key = "j", mods = "LEADER",       action=act{ActivatePaneDirection="Down"}},
  { key = "k", mods = "LEADER",       action=act{ActivatePaneDirection="Up"}},
  { key = "l", mods = "LEADER",       action=act{ActivatePaneDirection="Right"}},
  { key = "s", mods = "LEADER",       action=act{SplitVertical={domain="CurrentPaneDomain"}}},
  { key = "v", mods = "LEADER",       action=act{SplitHorizontal={domain="CurrentPaneDomain"}}},
  { key = "w", mods = "LEADER",       action=act{CloseCurrentTab={confirm=true}}},
  { key = "q", mods = "LEADER",       action=act{CloseCurrentPane={confirm=true}}},
  { key = "z", mods = "LEADER",       action="TogglePaneZoomState" },
  { key = "c", mods = "CTRL",         action=act.CopyTo 'Clipboard'},
  { key = "v", mods = "CTRL",         action=act.PasteFrom 'Clipboard'},
  { key = "c", mods = "CTRL|SHIFT",   action=act.SendKey{key = 'c', mods = 'CTRL'}},
}
config.set_environment_variables = {}

if wezterm.target_triple == 'aarch64-apple-darwin' then
  config.set_environment_variables.PATH = '/opt/homebrew/bin:' .. os.getenv 'PATH'
end

config.default_prog = {'nu'}

return config
