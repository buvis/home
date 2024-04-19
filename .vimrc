" .vimrc
" Main vim configuration
"
" Configuration inspired by:
" * https://github.com/nvie/vimrc/blob/master/vimrc
" * http://stevelosh.com/blog/2010/09/coming-home-to-vim/
" * http://vimcasts.org/episodes/archive/
" * https://www.youtube.com/playlist?list=PLwJS-G75vM7kFO-yUkyNphxSIdbi_1NKX
"
" ATTENTION: put comments on new line, so they are not interpreted as commands

" Here I add plugins only, see ~/.vim/plugin for more configuration files

" Fix paths on Windows
set runtimepath+=$HOME/.vim
set packpath+=$HOME/.vim

" Enable code completion by ALE (must by set before loading it)
let g:ale_completion_enabled=1
set omnifunc=ale#completion#OmniFunc

" Activate project's or vim's virtualenv
silent py3 << EOF
from pathlib import Path
venv_activator = Path("C:/Users/tbouska/AppData/Local/pypoetry/Cache/virtualenvs/buvis-vim-config-PvOqcZAR-py3.12", "Scripts", "activate_this.py")
print(venv_activator)
exec(open(venv_activator).read(), {'__file__': venv_activator})
EOF

filetype indent plugin on
syntax on

" Load help for all plugins
packloadall
silent! helptags ALL
