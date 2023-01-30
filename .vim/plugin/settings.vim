" settings.vim
" General settings


" Sane defaults (NeoVim) {{{
set autoindent
set autoread
set backspace=indent,eol,start
set belloff=all
set complete-=i
set display+=lastline
set formatoptions=tcqj
set history=10000
set incsearch
set laststatus=2
set ruler
set sessionoptions-=options
set showcmd
set sidescroll=1
set smarttab
set ttimeoutlen=50
set ttyfast
set viminfo+=!
set wildmenu
" }}}

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
set ff=unix
set fileencoding=utf-8
set termencoding=utf-8
set spell spelllang=en_gb
" }}}

" Focus automation {{{
" change working directory to buffer, so Ag searches in relevant context
set autochdir
" refresh file when changed somewhere else
set autoread
" save file on switching focus
set autowriteall
au FocusLost * :wa
" make argdo, bufdo, cfdo work on collection of buffers
set hidden

" }}}

" Folding {{{
" add a fold column
set foldcolumn=2
" enable folding
set foldenable
" start with everything unfolded
set foldlevelstart=0
" }}}

" Tab settings {{{
"     expand tabs by default (overloadable per file type later)
set expandtab
"     use multiple of shiftwidth when indenting with '<' and '>'
set shiftround
"     number of spaces to use for autoindenting
set shiftwidth=4
"     when hitting <BS>, pretend like a tab is removed, even if spaces
set softtabstop=4
"     a tab is four spaces
set tabstop=4
" }}}
