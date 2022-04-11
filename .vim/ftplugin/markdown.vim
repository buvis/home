" markdown.vim
" markdown specific settings

" register pymarkdown linter
call ale#linter#Define('markdown', {
\   'name': 'pymarkdown',
\   'executable': 'pymarkdown',
\   'lint_file': 1,
\   'output_stream': 'both',
\   'command': '%e -c $HOME/.pymarkdown.config.json scan %t',
\   'callback': 'buvis#functions#pymarkdownlint'
\})

" activate E-Prime in writegood
let b:ale_writegood_options = '--yes-eprime'

" syntax checker settings
let b:ale_linters = ['pymarkdown', 'writegood']

" highlight code blocks for given languages
let g:vim_markdown_fenced_languages = [
    \ 'html',
    \ 'css',
    \ 'scss',
    \ 'sql',
    \ 'js=javascript',
    \ 'json=javascript',
    \ 'javascript',
    \ 'go',
    \ 'python',
    \ 'ini',
    \ 'bash=sh',
    \ 'c',
    \ 'ruby'
    \ ]

" start unfolded
setlocal foldlevel=99

" switch on plaintext settings
call wincent#functions#plaintext()

" don't highlight syntax
setlocal synmaxcol=0

" don't conceal
let g:vim_markdown_conceal = 0
let g:vim_markdown_conceal_code_blocks = 0
let g:vim_markdown_math = 1

" start insert mode with current time
nnoremap <Leader>d 0i<CR><ESC>k"=strftime("%d.%m.%Y %H:%M - ")<ESC>pA

" save edits before folowing a link with ge
let g:vim_markdown_autowrite = 1

" open links in tabs
let g:vim_markdown_edit_url_in = 'tab'

" handle anchors in URL
let g:vim_markdown_follow_anchor = 1
