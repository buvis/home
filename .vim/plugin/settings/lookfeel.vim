" settings/lookfeel.vim
" Look and feel

" lightline.vim
" https://github.com/itchyny/lightline.vim
set laststatus=2
let g:lightline = {
      \ "colorscheme": "solarized",
      \ "background": "dark",
      \ }

" NeoSolarized
" https://github.com/overcache/NeoSolarized
if has("win32") || has("win64")
  set termguicolors
endif
set background=light
let g:neosolarized_italic=1
let g_neosolarized_termBoldAsBright=0
colorscheme NeoSolarized

" highlight the current line and column for quicker orientation
set cursorline
set cursorcolumn
