" python.vim
" Override settings for python file type
" Duplicate of after/ftplugin/python.vim, because Windows works differently

" Use ALE's completion
set omnifunc=ale#completion#OmniFunc
let b:ale_linters = {'python': ['ruff', 'pylsp']}
