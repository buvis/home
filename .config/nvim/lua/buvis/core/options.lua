local home = vim.env.HOME
local config = home .. '/.config/nvim'
local root = vim.env.USER == 'root'
local vi = vim.v.progname == 'vi'
local option = vim.opt

option.autoindent = true -- maintain indent of current line
option.backspace = 'indent,start,eol' -- allow unrestricted backspacing in insert mode
option.backup = false -- don't make backups before writing
option.backupcopy = 'yes' -- overwrite files to update, instead of renaming + rewriting
option.backupdir = config .. '/backup//' -- keep backup files out of the way (ie. if 'backup' is ever set)
option.backupdir = option.backupdir + '.' -- fallback
option.backupskip = option.backupskip + '*.re,*.rei' -- prevent bsb's watch mode from getting confused (if 'backup' is ever set)
option.belloff = 'all' -- never ring the bell for any reason
option.completeopt = 'menu' -- show completion menu (for nvim-cmp)
option.completeopt = option.completeopt + 'menuone' -- show menu even if there is only one candidate (for nvim-cmp)
option.completeopt = option.completeopt + 'noselect' -- don't automatically select canditate (for nvim-cmp)
option.cursorline = true -- highlight current line
option.diffopt = option.diffopt + 'foldcolumn:0' -- don't show fold column in diff view
option.directory = config .. '/nvim/swap//' -- keep swap files out of the way
option.directory = option.directory + '.' -- fallback
option.emoji = false -- don't assume all emoji are double width
option.expandtab = true -- always use spaces instead of tabs
option.fillchars = {
  diff = '∙', -- BULLET OPERATOR (U+2219, UTF-8: E2 88 99)
  eob = ' ', -- NO-BREAK SPACE (U+00A0, UTF-8: C2 A0) to suppress ~ at EndOfBuffer
  fold = '·', -- MIDDLE DOT (U+00B7, UTF-8: C2 B7)
  vert = '┃', -- BOX DRAWINGS HEAVY VERTICAL (U+2503, UTF-8: E2 94 83)
}
option.foldlevelstart = 99 -- start unfolded
option.foldmethod = 'indent' -- not as cool as syntax, but faster
option.foldtext = 'v:lua.wincent.foldtext()'
option.formatoptions = option.formatoptions + 'j' -- remove comment leader when joining comment lines
option.formatoptions = option.formatoptions + 'n' -- smart auto-indenting inside numbered lists
option.guifont = 'Source Code Pro Light:h13'
option.hidden = true -- allows you to hide buffers with unsaved changes without being prompted
option.inccommand = 'split' -- live preview of :s results
option.ignorecase = true -- ignore case in searches
option.joinspaces = false -- don't autoinsert two spaces after '.', '?', '!' for join command
option.laststatus = 2 -- always show status line
option.lazyredraw = true -- don't bother updating screen during macro playback
option.linebreak = true -- wrap long lines at characters in 'breakat'
option.list = true -- show whitespace
option.listchars = {
  nbsp = '⦸', -- CIRCLED REVERSE SOLIDUS (U+29B8, UTF-8: E2 A6 B8)
  extends = '»', -- RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK (U+00BB, UTF-8: C2 BB)
  precedes = '«', -- LEFT-POINTING DOUBLE ANGLE QUOTATION MARK (U+00AB, UTF-8: C2 AB)
  tab = '▷⋯', -- WHITE RIGHT-POINTING TRIANGLE (U+25B7, UTF-8: E2 96 B7) + MIDLINE HORIZONTAL ELLIPSIS (U+22EF, UTF-8: E2 8B AF)
  trail = '•', -- BULLET (U+2022, UTF-8: E2 80 A2)
}

if vi then
  option.loadplugins = false
end

option.modelines = 5 -- scan this many lines looking for modeline
option.number = true -- show line numbers in gutter
option.pumheight = 20 -- max number of lines to show in pop-up menu
option.pumblend = 10 -- pseudo-transparency for popup-menu
option.relativenumber = true -- show relative numbers in gutter
option.scrolloff = 3 -- start scrolling 3 lines before edge of viewport

if root then
  option.shada = '' -- Don't create root-owned files.
  option.shadafile = 'NONE'
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
  option.shada = "'0,<0,f0,n~/.config/nvim/shada"
end

option.shell = 'sh' -- shell to use for `!`, `:!`, `system()` etc.
option.shiftround = false -- don't always indent by multiple of shiftwidth
option.shiftwidth = 2 -- spaces per tab (when shifting)
option.shortmess = option.shortmess + 'A' -- ignore annoying swapfile messages
option.shortmess = option.shortmess + 'I' -- no splash screen
option.shortmess = option.shortmess + 'O' -- file-read message overwrites previous
option.shortmess = option.shortmess + 'T' -- truncate non-file messages in middle
option.shortmess = option.shortmess + 'W' -- don't echo "[w]"/"[written]" when writing
option.shortmess = option.shortmess + 'a' -- use abbreviations in messages eg. `[RO]` instead of `[readonly]`
option.shortmess = option.shortmess + 'c' -- completion messages
option.shortmess = option.shortmess + 'o' -- overwrite file-written messages
option.shortmess = option.shortmess + 't' -- truncate file messages at start
option.showbreak = '↳ ' -- DOWNWARDS ARROW WITH TIP RIGHTWARDS (U+21B3, UTF-8: E2 86 B3)
option.showcmd = false -- don't show extra info at end of command line
option.sidescroll = 0 -- sidescroll in jumps because terminals are slow
option.sidescrolloff = 3 -- same as scrolloff, but for columns
option.smartcase = true -- don't ignore case in searches if uppercase characters present
option.smarttab = true -- <tab>/<BS> indent/dedent in leading whitespace

if not vi then
  option.softtabstop = -1 -- use 'shiftwidth' for tab/bs at end of line
end

option.spellcapcheck = '' -- don't check for capital letters at start of sentence
option.splitbelow = true -- open horizontal splits below current window
option.splitright = true -- open vertical splits to the right of the current window
option.suffixes = option.suffixes - '.h' -- don't sort header files at lower priority
option.swapfile = false -- don't create swap files
option.switchbuf = 'usetab' -- try to reuse windows/tabs when switching buffers
option.synmaxcol = 200 -- don't bother syntax highlighting long lines
option.tabstop = 2 -- spaces per tab
option.termguicolors = true -- use guifg/guibg instead of ctermfg/ctermbg in terminal

if root then
  option.undofile = false -- don't create root-owned files
else
  option.undodir = config .. '/.undo//' -- keep undo files out of the way
  option.undodir = option.undodir + '.' -- fallback
  option.undofile = true -- actually use undo files
end

option.updatetime = 2000 -- CursorHold interval
option.updatecount = 0 -- update swapfiles every 80 typed chars
option.viewdir = config .. '/view' -- where to store files for :mkview
option.viewoptions = 'cursor,folds' -- save/restore just these (with `:{mk,load}view`)
option.virtualedit = 'block' -- allow cursor to move where there is no text in visual block mode
option.visualbell = true -- stop annoying beeping for non-error errors
option.whichwrap = 'b,h,l,s,<,>,[,],~' -- allow <BS>/h/l/<Left>/<Right>/<Space>, ~ to cross line boundaries
option.wildcharm = 26 -- ('<C-z>') substitute for 'wildchar' (<Tab>) in macros
option.wildignore = option.wildignore + '*.o,*.rej,*.so' -- patterns to ignore during file-navigation
option.wildmenu = true -- show options as list when switching buffers etc
option.wildmode = 'longest:full,full' -- shell-like autocomplete to unambiguous portion
option.winblend = 10 -- psuedo-transparency for floating windows
option.writebackup = false -- don't keep backups after writing

-- Highlight up to 255 columns (this is the current Vim max) beyond 'textwidth'
vim.opt_local.colorcolumn = '+' .. buvis.util.join(buvis.util.range(0, 254), ',+')
vim.api.nvim_set_hl(0, "EndOfBuffer", { link = "ColorColumn" })
