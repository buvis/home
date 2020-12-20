" lookfeel.vim
" Look and feel


scriptencoding utf-8

" airline statusline
let g:airline_theme='solarized'
"let g:airline_solarized_bg='dark'
let g:airline_powerline_fonts=1

" hide wide area after column 79
set colorcolumn=79
let &l:colorcolumn='+' . join(range(0, 254), ',+')

" activate and configure theme
if has("win32") || has("win64")
    set termguicolors
endif
set background=light
let g:neosolarized_italic=1
let g:neosolarized_termBoldAsBright = 0
colorscheme NeoSolarized

" highlight the current line and column for quicker orientation
set cursorline
set cursorcolumn

" hide (or at least make less obvious) the EndOfBuffer region
highlight! link EndOfBuffer ColorColumn

" fix quickfix window unreadable
highlight! QuickFixLine cterm=bold ctermbg=NONE

" draw full line between vertical splits
set fillchars+=vert:│

" blend indentline with cursorcolumn
let g:indentLine_bgcolor_term = 7
let g:indentLine_char = '┆'

" use more visually striking whitespace characters
" reference: https://unicode-table.com/en/
set list
set listchars=nbsp:⦸
set listchars+=tab:▷┅
set listchars+=extends:»
set listchars+=precedes:«
set listchars+=eol:¬
set listchars+=trail:░

" show line numbers
set number
set relativenumber

" show some context when scrolling
set scrolloff=3

" show command being typed
set showcmd

" update the interface more frequently
set updatetime=500
