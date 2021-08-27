" leader.vim
" Leader mappings


" set leader keys
let mapleader = "\<Space>"
let maplocalleader = "\\"

" run ArgWrap plugin
nnoremap <silent> <Leader>aw :ArgWrap<CR>

" manage configuration files
nnoremap <silent> <Leader>c :CtrlP ~/.vim<CR>
nnoremap <silent> <Leader>crc :e ~/.vimrc<CR>

" edit file, starting in same directory as current file
nnoremap <Leader>e :edit <C-R>=expand('%:p:h') . '/'<CR>

" fuzzy find inside project files
nnoremap <Leader>ff :Ag<CR>

" join all lines using ; (eg. to email list of people)
nnoremap <Leader>J :%s/\n/;/g<CR>

" redefine wincent/scalpel trigger
nmap <Leader>r <Plug>(Scalpel)

" strip whitespace
nnoremap <silent> <Leader>ss :call buvis#functions#stripspaces()<CR>

" clear search highlights
nmap <Leader><Space> <Plug>(LoupeClearHighlight)
