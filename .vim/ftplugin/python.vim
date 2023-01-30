" python.vim
" python specific settings


" syntax checker settings
let b:ale_linters = ['ruff']
let b:ale_fixers = [
    \ 'add_blank_lines_for_python_control_statements',
    \ 'black',
    \ 'ruff',
    \ 'yapf',
    \ ]

" start unfolded
set foldlevel=99

" tab settings
setlocal tabstop=4
setlocal softtabstop=4
setlocal shiftwidth=4
setlocal textwidth=79
setlocal expandtab
