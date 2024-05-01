if vim.loader then
  vim.loader.enable()
end

require('buvis')

-------------------------------------------------------------------------------
-- Options {{{1 ---------------------------------------------------------------
-------------------------------------------------------------------------------

local home = vim.env.HOME
local config = home .. '/.config/nvim'
local root = vim.env.USER == 'root'
local vi = vim.v.progname == 'vi'

vim.opt.autoindent = true -- maintain indent of current line
vim.opt.backspace = 'indent,start,eol' -- allow unrestricted backspacing in insert mode
vim.opt.backup = false -- don't make backups before writing
vim.opt.backupcopy = 'yes' -- overwrite files to update, instead of renaming + rewriting
vim.opt.backupdir = config .. '/backup//' -- keep backup files out of the way (ie. if 'backup' is ever set)
vim.opt.backupdir = vim.opt.backupdir + '.' -- fallback
vim.opt.backupskip = vim.opt.backupskip + '*.re,*.rei' -- prevent bsb's watch mode from getting confused (if 'backup' is ever set)
vim.opt.belloff = 'all' -- never ring the bell for any reason
vim.opt.completeopt = 'menu' -- show completion menu (for nvim-cmp)
vim.opt.completeopt = vim.opt.completeopt + 'menuone' -- show menu even if there is only one candidate (for nvim-cmp)
vim.opt.completeopt = vim.opt.completeopt + 'noselect' -- don't automatically select canditate (for nvim-cmp)
vim.opt.cursorline = true -- highlight current line
vim.opt.diffopt = vim.opt.diffopt + 'foldcolumn:0' -- don't show fold column in diff view
vim.opt.directory = config .. '/nvim/swap//' -- keep swap files out of the way
vim.opt.directory = vim.opt.directory + '.' -- fallback
vim.opt.emoji = false -- don't assume all emoji are double width
vim.opt.expandtab = true -- always use spaces instead of tabs
vim.opt.fillchars = {
  diff = '∙', -- BULLET OPERATOR (U+2219, UTF-8: E2 88 99)
  eob = ' ', -- NO-BREAK SPACE (U+00A0, UTF-8: C2 A0) to suppress ~ at EndOfBuffer
  fold = '·', -- MIDDLE DOT (U+00B7, UTF-8: C2 B7)
  vert = '┃', -- BOX DRAWINGS HEAVY VERTICAL (U+2503, UTF-8: E2 94 83)
}
vim.opt.foldlevelstart = 99 -- start unfolded
vim.opt.foldmethod = 'indent' -- not as cool as syntax, but faster
vim.opt.foldtext = 'v:lua.wincent.foldtext()'
vim.opt.formatoptions = vim.opt.formatoptions + 'j' -- remove comment leader when joining comment lines
vim.opt.formatoptions = vim.opt.formatoptions + 'n' -- smart auto-indenting inside numbered lists
vim.opt.guifont = 'Source Code Pro Light:h13'
vim.opt.hidden = true -- allows you to hide buffers with unsaved changes without being prompted
vim.opt.inccommand = 'split' -- live preview of :s results
vim.opt.ignorecase = true -- ignore case in searches
vim.opt.joinspaces = false -- don't autoinsert two spaces after '.', '?', '!' for join command
vim.opt.laststatus = 2 -- always show status line
vim.opt.lazyredraw = true -- don't bother updating screen during macro playback
vim.opt.linebreak = true -- wrap long lines at characters in 'breakat'
vim.opt.list = true -- show whitespace
vim.opt.listchars = {
  nbsp = '⦸', -- CIRCLED REVERSE SOLIDUS (U+29B8, UTF-8: E2 A6 B8)
  extends = '»', -- RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK (U+00BB, UTF-8: C2 BB)
  precedes = '«', -- LEFT-POINTING DOUBLE ANGLE QUOTATION MARK (U+00AB, UTF-8: C2 AB)
  tab = '▷⋯', -- WHITE RIGHT-POINTING TRIANGLE (U+25B7, UTF-8: E2 96 B7) + MIDLINE HORIZONTAL ELLIPSIS (U+22EF, UTF-8: E2 8B AF)
  trail = '•', -- BULLET (U+2022, UTF-8: E2 80 A2)
}

if vi then
  vim.opt.loadplugins = false
end

vim.opt.modelines = 5 -- scan this many lines looking for modeline
vim.opt.number = true -- show line numbers in gutter
vim.opt.pumheight = 20 -- max number of lines to show in pop-up menu
vim.opt.pumblend = 10 -- pseudo-transparency for popup-menu
vim.opt.relativenumber = true -- show relative numbers in gutter
vim.opt.scrolloff = 3 -- start scrolling 3 lines before edge of viewport

if root then
  vim.opt.shada = '' -- Don't create root-owned files.
  vim.opt.shadafile = 'NONE'
else
  -- Defaults:
  --   Neovim: !,'100,<50,s10,h
  --
  -- - ! save/restore global variables (only all-uppercase variables)
  -- - '100 save/restore marks from last 100 files
  -- - <50 save/restore 50 lines from each register
  -- - s10 max item size 10KB
  -- - h do not save/restore 'hlsearch' setting
  --
  -- Our overrides:
  -- - '0 store marks for 0 files
  -- - <0 don't save registers
  -- - f0 don't store file marks
  -- - n: store in ~/.config/nvim/
  --
  vim.opt.shada = "'0,<0,f0,n~/.config/nvim/shada"
end

vim.opt.shell = 'sh' -- shell to use for `!`, `:!`, `system()` etc.
vim.opt.shiftround = false -- don't always indent by multiple of shiftwidth
vim.opt.shiftwidth = 2 -- spaces per tab (when shifting)
vim.opt.shortmess = vim.opt.shortmess + 'A' -- ignore annoying swapfile messages
vim.opt.shortmess = vim.opt.shortmess + 'I' -- no splash screen
vim.opt.shortmess = vim.opt.shortmess + 'O' -- file-read message overwrites previous
vim.opt.shortmess = vim.opt.shortmess + 'T' -- truncate non-file messages in middle
vim.opt.shortmess = vim.opt.shortmess + 'W' -- don't echo "[w]"/"[written]" when writing
vim.opt.shortmess = vim.opt.shortmess + 'a' -- use abbreviations in messages eg. `[RO]` instead of `[readonly]`
vim.opt.shortmess = vim.opt.shortmess + 'c' -- completion messages
vim.opt.shortmess = vim.opt.shortmess + 'o' -- overwrite file-written messages
vim.opt.shortmess = vim.opt.shortmess + 't' -- truncate file messages at start
vim.opt.showbreak = '↳ ' -- DOWNWARDS ARROW WITH TIP RIGHTWARDS (U+21B3, UTF-8: E2 86 B3)
vim.opt.showcmd = false -- don't show extra info at end of command line
vim.opt.sidescroll = 0 -- sidescroll in jumps because terminals are slow
vim.opt.sidescrolloff = 3 -- same as scrolloff, but for columns
vim.opt.smartcase = true -- don't ignore case in searches if uppercase characters present
vim.opt.smarttab = true -- <tab>/<BS> indent/dedent in leading whitespace

if not vi then
  vim.opt.softtabstop = -1 -- use 'shiftwidth' for tab/bs at end of line
end

vim.opt.spellcapcheck = '' -- don't check for capital letters at start of sentence
vim.opt.splitbelow = true -- open horizontal splits below current window
vim.opt.splitright = true -- open vertical splits to the right of the current window
vim.opt.suffixes = vim.opt.suffixes - '.h' -- don't sort header files at lower priority
vim.opt.swapfile = false -- don't create swap files
vim.opt.switchbuf = 'usetab' -- try to reuse windows/tabs when switching buffers
vim.opt.synmaxcol = 200 -- don't bother syntax highlighting long lines
vim.opt.tabstop = 2 -- spaces per tab
vim.opt.termguicolors = true -- use guifg/guibg instead of ctermfg/ctermbg in terminal

if root then
  vim.opt.undofile = false -- don't create root-owned files
else
  vim.opt.undodir = config .. '/.undo//' -- keep undo files out of the way
  vim.opt.undodir = vim.opt.undodir + '.' -- fallback
  vim.opt.undofile = true -- actually use undo files
end

vim.opt.updatetime = 2000 -- CursorHold interval
vim.opt.updatecount = 0 -- update swapfiles every 80 typed chars
vim.opt.viewdir = config .. '/view' -- where to store files for :mkview
vim.opt.viewoptions = 'cursor,folds' -- save/restore just these (with `:{mk,load}view`)
vim.opt.virtualedit = 'block' -- allow cursor to move where there is no text in visual block mode
vim.opt.visualbell = true -- stop annoying beeping for non-error errors
vim.opt.whichwrap = 'b,h,l,s,<,>,[,],~' -- allow <BS>/h/l/<Left>/<Right>/<Space>, ~ to cross line boundaries
vim.opt.wildcharm = 26 -- ('<C-z>') substitute for 'wildchar' (<Tab>) in macros
vim.opt.wildignore = vim.opt.wildignore + '*.o,*.rej,*.so' -- patterns to ignore during file-navigation
vim.opt.wildmenu = true -- show options as list when switching buffers etc
vim.opt.wildmode = 'longest:full,full' -- shell-like autocomplete to unambiguous portion
vim.opt.winblend = 10 -- psuedo-transparency for floating windows
vim.opt.writebackup = false -- don't keep backups after writing

-- Highlight up to 255 columns (this is the current Vim max) beyond 'textwidth'
vim.opt_local.colorcolumn = '+' .. buvis.util.join(buvis.util.range(0, 254), ',+')
vim.api.nvim_set_hl(0, "EndOfBuffer", { link = "ColorColumn" })

-------------------------------------------------------------------------------
-- Globals {{{1 ---------------------------------------------------------------
-------------------------------------------------------------------------------

vim.g.mapleader = ' '
vim.g.maplocalleader = '\\'

-- Extension -> filetype mappings.
vim.g.filetype_m = 'objc'
vim.g.filetype_pl = 'prolog'

-- Stark highlighting is enough to see the current match; don't need the
-- centering, which can be annoying.
vim.g.LoupeCenterResults = 0

-- Using <F13> instead of actual <Nop> to avoid messing with "<" mappings.
-- (<Nop> works fine in RHS of mappings, but on LHS, Vim treats it like "<" +
-- "n" + "o" + "p" + ">".)
local nop = '<F13>'

-- And it turns out that if we're going to turn off the centering, we don't even
-- need the mappings; see: https://github.com/wincent/loupe/pull/15
vim.api.nvim_set_keymap('n', nop .. '<F1>', '<Plug>(LoupeN)', {})
vim.api.nvim_set_keymap('n', nop .. '<F2>', '<Plug>(Loupen)', {})

-- Stop Ferret from binding <Leader>l, which we want to keep for interactions
-- with the language server client (the rare-ish times I want :Lack, I can just
-- type it out).
vim.api.nvim_set_keymap('', nop .. '<F3>', '<Plug>(FerretLack)', {})

-- Turn off most of the features of this plug-in; I really just want the folding.
vim.g.vim_markdown_override_foldtext = 0
vim.g.vim_markdown_no_default_key_mappings = 1
vim.g.vim_markdown_emphasis_multiline = 0
vim.g.vim_markdown_conceal = 0
vim.g.vim_markdown_conceal_code_blocks = 0
vim.g.vim_markdown_frontmatter = 1
vim.g.vim_markdown_new_list_item_indent = 0

if vim.fn.filereadable('/usr/local/bin/python3') == 1 then
  -- Avoid search, speeding up start-up.
  vim.g.python3_host_prog = '/usr/local/bin/python3'
end

-- Normally <Leader>s (mnemonic: "[s]earch");
-- use <Leader>f instead (mnemonic: "[f]ind")
vim.api.nvim_set_keymap('n', '<Leader>f', '<Plug>(FerretAckWord)', {})

-- Normally <Leader>r (mnemonic: "[r]eplace");
-- use <Leader>s (mnemonic: "[s]ubstitute") instead.
vim.api.nvim_set_keymap('n', '<Leader>s', '<Plug>(FerretAcks)', {})

-- Allow for per-machine overrides.
local hostname = vim.fn.substitute(vim.fn.hostname(), '\\..*', '', '')
local overrides = {
  config .. '/host/' .. hostname .. '.vim',
  config .. '/host/' .. hostname .. '.lua',
  config .. '/init-local.vim',
  config .. '/init-local.lua',
}
for _, override in ipairs(overrides) do
  if vim.fn.filereadable(override) == 1 then
    vim.cmd('source ' .. override)
  end
end

-------------------------------------------------------------------------------
-- Plugins {{{1 ---------------------------------------------------------------
-------------------------------------------------------------------------------
if vim.o.loadplugins then
  buvis.plugin.load('NeoSolarized.nvim')
  buvis.plugin.load('nvim-tmux-navigation')
  buvis.plugin.load('replay')

  -- Lazy because it adds a slow BufEnter autocmd.
  buvis.plugin.lazy('nvim-tree.lua', {
    afterload = function()
      require('nvim-tree').setup()
    end,
    commands = {
      'NvimTreeFindFile',
      'NvimTreeToggle',
      'NvimTreeOpen',
   },
    keymap = {
      { 'n', '<LocalLeader>f', ':NvimTreeFindFile<CR>', { silent = true } },
      { 'n', '<LocalLeader>t', ':NvimTreeToggle<CR>', { silent = true } },
    },
  })
end

-- Automatic, language-dependent indentation, syntax coloring and other
-- functionality.
--
-- Must come *after* the `:packadd!` calls above otherwise the contents of
-- package "ftdetect" directories won't be evaluated.
vim.cmd('filetype indent plugin on')
vim.cmd('syntax on')

-------------------------------------------------------------------------------
-- Footer {{{1 ----------------------------------------------------------------
-------------------------------------------------------------------------------

--[[

After this file is sourced, plugin code will be evaluated (eg.
~/.config/nvim/plugin/* and so on ). See ~/.config/nvim/after for files
evaluated after that.  See `:scriptnames` for a list of all scripts, in
evaluation order.

Launch Neovim with `nvim --startuptime nvim.log` for profiling info.

To see all leader mappings, including those from plugins:

    nvim -c 'map <Leader>'
    nvim -c 'map <LocalLeader>'

--]]

-------------------------------------------------------------------------------
-- Modeline {{{1 --------------------------------------------------------------
-------------------------------------------------------------------------------

-- vim: foldmethod=marker
