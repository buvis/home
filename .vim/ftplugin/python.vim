" python.vim
" Override plugins' configuration for python filetype

" Use ALE's completion
set omnifunc=ale#completion#OmniFunc
let b:ale_linters = {'python': ['ruff', 'pylsp']}
