" python.vim
" Override settings for python file type

" Use ALE's completion
set omnifunc=ale#completion#OmniFunc
let b:ale_linters = {'python': ['ruff', 'pylsp']}

