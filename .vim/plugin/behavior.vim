" behavior.vim
" Editing behavior settings


" When opening a new line
set autoindent
set smartindent

" When entering something in brackets
set showmatch

" When typing to command line
"     improve command line completion
set wildmenu
"set wildmode=list:longest,full

" When joining lines
"     remove comment leader when joining comment lines
set formatoptions+=j
"     don't autoinsert two spaces after '.', '?', '!' for join command
set nojoinspaces
