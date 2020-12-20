" markdown.vim
" markdown specific settings


" color yaml frontmatter
let g:vim_markdown_frontmatter = 1

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
    \ 'bash=sh',
    \ 'c',
    \ 'ruby'
    \ ]

" fold by expression using vim-markdown-folding plugin
setlocal foldmethod=expr
let g:markdown_folding = 1
set foldexpr=NestedMarkdownFolds()

" start unfolded
setlocal foldlevel=99

" switch on plaintext settings
call wincent#functions#plaintext()

" don't highlight syntax
setlocal synmaxcol=0

" don't conceal
let g:vim_markdown_conceal = 0

" start insert mode with current time
nnoremap <Leader>d 0i<CR><ESC>k"=strftime("%d.%m.%Y %H:%M - ")<ESC>pA
