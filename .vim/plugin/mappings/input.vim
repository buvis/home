" input.vim
" Input mode

" disable arrow keys to resist the temptation
inoremap <up> <nop>
inoremap <down> <nop>
inoremap <left> <nop>
inoremap <right> <nop>

" cycle completion suggestions using Tab
inoremap <expr><tab> pumvisible() ? "\<c-n>" : "\<tab>"
