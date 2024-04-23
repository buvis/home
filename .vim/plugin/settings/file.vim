" settings/file.vim
" General settings for files

" Auxiliary files {{{
" do not keep backup files, it's 70's style cluttering
set nobackup
" do not write annoying intermediate swap files
set noswapfile
" do not write out changes via backup files
set nowritebackup
" keep a persistent backup file
set undofile
" centralize undo files location
set undodir=~/.vim/.undo//
" use more levels of undo
set undolevels=1000
" lookup tags in parent directories
set tags=tags;
" }}}

" File properties {{{
set encoding=utf-8
set fileformat=unix
set fileencoding=utf-8
set termencoding=utf-8
set spell spelllang=en_gb
" }}}
