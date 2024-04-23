local leader = buvis.mappings.leader

local autocmds = {}

local number_flag = leader.number_flag
local captured_settings = {}

-- stylua: ignore
local focused_colorcolumn = '+' .. table.concat({
  '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12',
  '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23',
  '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34',
  '35', '36', '37', '38', '39', '40', '41', '42', '43', '44', '45',
  '46', '47', '48', '49', '50', '51', '52', '53', '54', '55', '56',
  '57', '58', '59', '60', '61', '62', '63', '64', '65', '66', '67',
  '68', '69', '70', '71', '72', '73', '74', '75', '76', '77', '78',
  '79', '80', '81', '82', '83', '84', '85', '86', '87', '88', '89',
  '90', '91', '92', '93', '94', '95', '96', '97', '98', '99', '100',
  '101', '102', '103', '104', '105', '106', '107', '108', '109', '110',
  '111', '112', '113', '114', '115', '116', '117', '118', '119', '120',
  '121', '122', '123', '124', '125', '126', '127', '128', '129', '130',
  '131', '132', '133', '134', '135', '136', '137', '138', '139', '140',
  '141', '142', '143', '144', '145', '146', '147', '148', '149', '150',
  '151', '152', '153', '154', '155', '156', '157', '158', '159', '160',
  '161', '162', '163', '164', '165', '166', '167', '168', '169', '170',
  '171', '172', '173', '174', '175', '176', '177', '178', '179', '180',
  '181', '182', '183', '184', '185', '186', '187', '188', '189', '190',
  '191', '192', '193', '194', '195', '196', '197', '198', '199', '200',
  '201', '202', '203', '204', '205', '206', '207', '208', '209', '210',
  '211', '212', '213', '214', '215', '216', '217', '218', '219', '220',
  '221', '222', '223', '224', '225', '226', '227', '228', '229', '230',
  '231', '232', '233', '234', '235', '236', '237', '238', '239', '240',
  '241', '242', '243', '244', '245', '246', '247', '248', '249', '250',
  '251', '252', '253', '254'
}, ',+')

local winhighlight_blurred = table.concat({
  'CursorLineNr:LineNr',
  'EndOfBuffer:ColorColumn',
  'IncSearch:ColorColumn',
  'Normal:ColorColumn',
  'NormalNC:ColorColumn',
  'Search:ColorColumn',
  'SignColumn:ColorColumn',
}, ',')

-- Helper to Save settings for later restoration; see `ownsyntax` below.
local capture = function(filetype)
  if not captured_settings[filetype] then
    -- We haven't captured settings for this filetype yet.
    captured_settings[filetype] = {
      spell = vim.wo.spell,
      spellcapcheck = vim.bo.spellcapcheck,
      spellfile = vim.bo.spellfile,
      spelllang = vim.bo.spelllang,
    }
    -- TODO: figure out how/when/if to update one of these objects
  end
end

-- As described in a7e4d8b8383a375d124, `ownsyntax` resets spelling settings, so
-- we capture and restore them. Note that there is some trickiness here because
-- multiple autocmds can trigger "focus" or "blur" operations; this means that
-- we can't just naively save and restore: we have to use a flag to make sure
-- that we only capture the initial state, and we also have to do this in a
-- filetype-aware way, because different filetypes can have different settings
-- (and the same window can be used to show buffers with different filetypes).
local ownsyntax = function(focussing)
  local blurring = not focussing

  local filetype = vim.bo.filetype
  if focussing and filetype ~= '' then
    if vim.w.current_syntax == nil then
      -- `ownsyntax` is off.
      capture(filetype)
      vim.cmd('ownsyntax on')
    end

    if captured_settings[filetype] then
      vim.opt_local.spell = captured_settings[filetype].spell or false
      vim.opt_local.spellcapcheck = captured_settings[filetype].spellcapcheck or ''
      vim.opt_local.spellfile = captured_settings[filetype].spellfile or ''
      vim.opt_local.spelllang = captured_settings[filetype].spelllang or 'en'
    end
  elseif blurring and filetype ~= '' then
    capture(filetype)

    if vim.w.current_syntax ~= nil then
      -- `ownsyntax` is on.
      vim.cmd('ownsyntax off')
    end

    -- Suppress spelling in blurred buffer.
    vim.wo.spell = false
  end
end

local should_mkview = function()
  return vim.bo.buftype == ''
    and autocmds.mkview_filetype_blacklist[vim.bo.filetype] == nil
    and vim.fn.exists('$SUDO_USER') == 0 -- Don't create root-owned files.
end

local focus_window = function()
  local filetype = vim.bo.filetype

  -- Turn on relative numbers, unless user has explicitly changed numbering.
  if filetype ~= '' and autocmds.number_blacklist[filetype] ~= true and vim.w[number_flag] == nil then
    vim.wo.number = true
    vim.wo.relativenumber = true
  end

  vim.api.nvim_set_hl(0, "EndOfBuffer", { link = "ColorColumn" })

  if filetype == '' or autocmds.winhighlight_filetype_blacklist[filetype] ~= true then
    vim.wo.winhighlight = ''
  end
  if filetype == '' or autocmds.colorcolumn_filetype_blacklist[filetype] ~= true then
    vim.wo.colorcolumn = focused_colorcolumn
  end
  if filetype == '' or autocmds.ownsyntax_filetypes[filetype] ~= true then
    ownsyntax(true)
  end
  if filetype == '' then
    vim.wo.list = true
  else
    local list = autocmds.list_filetypes[filetype]
    vim.wo.list = list == nil and true or list
  end
  local conceallevel = autocmds.conceallevel_filetypes[filetype] or 2
  vim.wo.conceallevel = conceallevel
  buvis.statusline.focus_statusline()
end

local blur_window = function()
  local filetype = vim.bo.filetype

  -- Turn off relative numbers (and turn on non-relative numbers), unless user
  -- has explicitly changed the numbering.
  if filetype ~= '' and autocmds.number_blacklist[filetype] ~= true and vim.w[number_flag] == nil then
    vim.wo.number = true
    vim.wo.relativenumber = false
  end

  if filetype == '' or autocmds.winhighlight_filetype_blacklist[filetype] ~= true then
    vim.wo.winhighlight = winhighlight_blurred
  end
  if filetype == '' or autocmds.ownsyntax_filetypes[filetype] ~= true then
    ownsyntax(false)
  end
  if filetype == '' then
    vim.wo.list = false
  else
    local list = autocmds.list_filetypes[filetype]
    if list == nil then
      vim.wo.list = false
    else
      vim.wo.list = list
    end
  end
  if filetype == '' or autocmds.conceallevel_filetypes[filetype] == nil then
    vim.wo.conceallevel = 0
  end
  buvis.statusline.blur_statusline()
end

-- http://vim.wikia.com/wiki/Make_views_automatic
local mkview = function()
  if should_mkview() then
    local success, err = pcall(function()
      if vim.fn.haslocaldir() == 1 then
        -- We never want to save an :lcd command, so hack around it...
        vim.cmd('cd -')
        vim.cmd('mkview')
        vim.cmd('lcd -')
      else
        vim.cmd('mkview')
      end
    end)
    if not success then
      if
        err:find('%f[%w]E32%f[%W]') == nil -- No file name; could be no buffer (eg. :checkhealth)
        and err:find('%f[%w]E186%f[%W]') == nil -- No previous directory: probably a `git` operation.
        and err:find('%f[%w]E190%f[%W]') == nil -- Could be name or path length exceeding NAME_MAX or PATH_MAX.
        and err:find('%f[%w]E5108%f[%W]') == nil
      then
        error(err)
      end
    end
  end
end

local set_cursorline = function(active)
  local filetype = vim.bo.filetype
  if autocmds.cursorline_blacklist[filetype] ~= true then
    vim.wo.cursorline = active
  end
end

autocmds.buf_enter = function()
  focus_window()
end

autocmds.buf_leave = function()
  mkview()
end

autocmds.buf_win_enter = function()
  if should_mkview() then
    vim.cmd('silent! loadview')
    vim.cmd('silent! ' .. vim.fn.line('.') .. 'foldopen!')
  end
end

autocmds.buf_write_post = function()
  mkview()
end

autocmds.file_type = function(a)
  local filetype = vim.fn.expand('<amatch>')
  capture(filetype)
end

autocmds.focus_gained = function()
  focus_window()
end

autocmds.focus_lost = function()
  blur_window()
end

autocmds.insert_enter = function()
  set_cursorline(false)
end

autocmds.insert_leave = function()
  set_cursorline(true)
end

autocmds.vim_enter = function()
  set_cursorline(true)
  focus_window()
end

autocmds.win_enter = function()
  set_cursorline(true)
  focus_window()
end

autocmds.win_leave = function()
  set_cursorline(false)
  blur_window()
  mkview()
end

-- Don't use colorcolumn when these filetypes get focus (we want them to appear
-- full-width irrespective of 'textwidth').
autocmds.colorcolumn_filetype_blacklist = {
  ['CommandTMatchListing'] = true,
  ['CommandTPrompt'] = true,
  ['CommandTTitle'] = true,
  ['command-t'] = true,
  ['diff'] = true,
  ['dirvish'] = true,
  ['fugitiveblame'] = true,
  ['undotree'] = true,
  ['qf'] = true,
  ['sagahover'] = true,
}

-- Don't mess with 'conceallevel' for these.
autocmds.conceallevel_filetypes = {
  ['dirvish'] = 2,
  ['help'] = 2,
}

autocmds.cursorline_blacklist = {
  ['CommandTMatchListing'] = true,
  ['CommandTPrompt'] = true,
  ['CommandTTitle'] = true,
  ['command-t'] = true,
}

-- Don't use 'winhighlight' to make these filetypes seem blurred.
autocmds.winhighlight_filetype_blacklist = {
  ['CommandTMatchListing'] = true,
  ['CommandTPrompt'] = true,
  ['CommandTTitle'] = true,
  ['diff'] = true,
  ['fugitiveblame'] = true,
  ['undotree'] = true,
  ['qf'] = true,
  ['sagahover'] = true,
}

-- Force 'list' (when `true`) or 'nolist' (when `false`) for these.
autocmds.list_filetypes = {
  ['CommandTMatchListing'] = false,
  ['CommandTPrompt'] = false,
  ['CommandTTitle'] = false,
  ['command-t'] = false,
  ['help'] = false,
  ['shellbot'] = false,
}

autocmds.mkview_filetype_blacklist = {
  ['diff'] = true,
  ['gitcommit'] = true,
  ['hgcommit'] = true,
}

-- Don't mess with numbers in these filetypes.
autocmds.number_blacklist = {
  ['CommandTMatchListing'] = true,
  ['CommandTPrompt'] = true,
  ['CommandTTitle'] = true,
  ['command-t'] = true,
  ['diff'] = true,
  ['fugitiveblame'] = true,
  ['help'] = true,
  ['qf'] = true,
  ['sagahover'] = true,
  ['shellbot'] = true,
  ['undotree'] = true,
}

-- Don't do "ownsyntax on/off" for these.
autocmds.ownsyntax_filetypes = {
  ['CommandTMatchListing'] = true,
  ['CommandTPrompt'] = true,
  ['CommandTTitle'] = true,
  ['NvimTree'] = true,
  ['dirvish'] = true,
  ['help'] = true,
  ['qf'] = true,
}

return autocmds
