" normal.vim
" Normal mode mappings


" fix non-intuitive line up/down movement over wrapped lines
noremap <silent> <expr> j (v:count == 0 ? 'gj' : 'j')
noremap <silent> <expr> k (v:count == 0 ? 'gk' : 'k')

" yank to system clipboard
nnoremap Y "*y

" show NERDTree (through vim-vinegar)
nmap = <Plug>VinegarUp

" fix dot moving the cursor
nmap . .`[

" make folding shortcut easy to remember
nnoremap <Tab> za
vnoremap <Tab> za

" create new zettel
nnoremap <leader>zn :ZettelNew<space>"insert title"

" find and open a zettel
nnoremap <leader>zo :ZettelOpen<CR>

" get highlight group under cursor
map <F10> :echo "hi<" . synIDattr(synID(line("."),col("."),1),"name") . '> trans<'
\ . synIDattr(synID(line("."),col("."),0),"name") . "> lo<"
\ . synIDattr(synIDtrans(synID(line("."),col("."),1)),"name") . ">"<CR>

" map arrow keys for moving in quickfix and location windows
nmap <silent> <left> <esc>:cprev<cr>
nmap <silent> <right> <esc>:cnext<cr>
nmap <silent> <up> <Plug>(ale_previous_wrap)
nmap <silent> <down> <Plug>(ale_next_wrap)
