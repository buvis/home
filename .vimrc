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

" Fix paths in Windows
set runtimepath+=$HOME/.vim
set packpath+=$HOME/.vim

" Activate project's or vim's virtualenv
" Prerequisites:
" 1) vim must be able to find python3 (check :version for the compilation
" flag)
" 2) poetry was installed to the environment from previous step
" 3) you created vim's virtualenv by running `poetry install` in `~/.vim`
silent py3 << EOF
from pathlib import Path
import subprocess

venv_dir_stdout = subprocess.run(["poetry", "--directory", Path(Path.home()/".vim"), "env","info","--path"], stdout=subprocess.PIPE)
venv_dir = Path(venv_dir_stdout.stdout.decode('utf-8').strip())

if not venv_dir.is_dir():
  print(f"Can't find vim's virtualenv. Run `poetry install` in ~/.vim", file=sys.stderr)
else:
  venv_activator = Path(venv_dir, "Scripts", "activate_this.py")
  if venv_activator.is_file():
    exec(open(venv_activator).read(), {'__file__': venv_activator})
  else:
    venv_activator = Path(venv_dir, "bin", "activate_this.py")
    if venv_activator.is_file():
      exec(open(venv_activator).read(), {'__file__': venv_activator})
    else:
      print(f"Can't activate vim's virtualenv at {venv_dir}", file=sys.stderr)
EOF

" Enable code completion by ALE (must by set before loading it)
let g:ale_completion_enabled=1

" Enable filetype specific scripts
filetype indent plugin on
syntax on

" Load plugins from ~/.vim/pack/plugins/start and generate help
packloadall
silent! helptags ALL
