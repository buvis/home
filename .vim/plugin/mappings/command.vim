" command.vim
" Command mode mappings


" faster jumps in commandline
cnoremap <C-a> <Home>
cnoremap <C-e> <End>

" replace %% in commandline by current buffer directory path
cnoremap <expr> %% getcmdtype() == ':' ? expand('%:h').'/' : '%%'
