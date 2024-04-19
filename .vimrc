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

" Neosolarized theme
" https://github.com/iCyMind/NeoSolarized
packadd! NeoSolarized

" Asynchronous Lint Engine
" https://github.com/dense-analysis/ale
packadd! ale

filetype indent plugin on
syntax on

" Load help for all plugins
packloadall
silent! helptags ALL
