local wezterm = require("wezterm")

local config = {
    audible_bell = "Disabled",
    check_for_updates = false,
    color_scheme = "Builtin Solarized Dark",
    inactive_pane_hsb = {
        hue = 0.45,
        saturation = 0.75,
        brightness = 0.44,
    },
    font_size = 10.5,
    launch_menu = {},
    leader = { key="\\" },
    disable_default_key_bindings = true,
    keys = {
        -- Send "CTRL-A" to the terminal when pressing CTRL-A, CTRL-A
        { key = "a", mods = "LEADER|CTRL",  action=wezterm.action{SendString="\x01"}},
        { key = "s", mods = "LEADER",       action=wezterm.action{SplitVertical={domain="CurrentPaneDomain"}}},
        { key = "v",mods = "LEADER",       action=wezterm.action{SplitHorizontal={domain="CurrentPaneDomain"}}},
        { key = "z", mods = "LEADER",       action="TogglePaneZoomState" },
        { key = "c", mods = "LEADER",       action=wezterm.action{SpawnTab="CurrentPaneDomain"}},
        { key = "h", mods = "CTRL",       action=wezterm.action{ActivatePaneDirection="Left"}},
        { key = "j", mods = "CTRL",       action=wezterm.action{ActivatePaneDirection="Down"}},
        { key = "k", mods = "CTRL",       action=wezterm.action{ActivatePaneDirection="Up"}},
        { key = "l", mods = "CTRL",       action=wezterm.action{ActivatePaneDirection="Right"}},
        { key = "H", mods = "CTRL|SHIFT", action=wezterm.action{AdjustPaneSize={"Left", 5}}},
        { key = "J", mods = "CTRL|SHIFT", action=wezterm.action{AdjustPaneSize={"Down", 5}}},
        { key = "K", mods = "CTRL|SHIFT", action=wezterm.action{AdjustPaneSize={"Up", 5}}},
        { key = "L", mods = "CTRL|SHIFT", action=wezterm.action{AdjustPaneSize={"Right", 5}}},
        { key = "1", mods = "LEADER",       action=wezterm.action{ActivateTab=0}},
        { key = "2", mods = "LEADER",       action=wezterm.action{ActivateTab=1}},
        { key = "3", mods = "LEADER",       action=wezterm.action{ActivateTab=2}},
        { key = "4", mods = "LEADER",       action=wezterm.action{ActivateTab=3}},
        { key = "5", mods = "LEADER",       action=wezterm.action{ActivateTab=4}},
        { key = "6", mods = "LEADER",       action=wezterm.action{ActivateTab=5}},
        { key = "7", mods = "LEADER",       action=wezterm.action{ActivateTab=6}},
        { key = "8", mods = "LEADER",       action=wezterm.action{ActivateTab=7}},
        { key = "9", mods = "LEADER",       action=wezterm.action{ActivateTab=8}},
        { key = "w", mods = "LEADER",       action=wezterm.action{CloseCurrentTab={confirm=true}}},
        { key = "x", mods = "LEADER",       action=wezterm.action{CloseCurrentPane={confirm=true}}},
        { key = "n", mods="SHIFT|CTRL",     action="ToggleFullScreen" },
        { key ="v",  mods="SHIFT|CTRL",    action=wezterm.action.PasteFrom 'Clipboard'},
        { key ="c",  mods="SHIFT|CTRL",    action=wezterm.action.CopyTo 'Clipboard'},
        { key = "+", mods="SHIFT|CTRL",     action="IncreaseFontSize" },
        { key = "-", mods="SHIFT|CTRL",     action="DecreaseFontSize" },
        { key = "0", mods="SHIFT|CTRL",     action="ResetFontSize" },
    },
    set_environment_variables = {},
}

config.default_prog = {'nu'}

return config
