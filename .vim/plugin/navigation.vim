" navigation.vim
" Navigation

" in WSL, open URL in host system
if executable('BrowserSelect.exe')
    let g:netrw_browsex_viewer='BrowserSelect.exe'
endif

" list files to ignore in NERDTree
let NERDTreeIgnore = ['\.pyc$', '\~$']

" open new splits in the expected direction
set splitbelow
set splitright
