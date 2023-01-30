" lsp.vim
" Language Server Protocol


" python
if executable('pylsp')
    " use this command when troubleshooting:
    " 'cmd': {server_info->['pylsp', '-v', '--log-file', '/Users/bob/vim-lsp-pylsp.log']},
    au User lsp_setup call lsp#register_server({
        \ 'name': 'pylsp',
        \ 'cmd': {server_info->['pylsp']},
        \ 'workspace_config': {'pylsp': {'plugins': {'jedi_completion': {'fuzzy': v:true, 'eager': v:true}}}},
        \ 'allowlist': ['python'],
        \ })
endif

" svelte
" HOWTO: Get path to node_modules for use in 'cmd' below: `npm root -g`
au User lsp_setup call lsp#register_server({
    \ 'name': 'svelte-language-server',
    \ 'cmd': {server_info->[&shell, &shellcmdflag, '/usr/local/lib/node_modules/svelte-language-server/bin/server.js --stdio']},
    \ 'allowlist': ['svelte'],
    \ })

" vim-lsp init buffer
function! s:on_lsp_buffer_enabled() abort
    setlocal signcolumn=yes
    if exists('+tagfunc') | setlocal tagfunc=lsp#tagfunc | endif
    nmap <buffer> gd <plug>(lsp-definition)
    nmap <buffer> gs <plug>(lsp-document-symbol-search)
    nmap <buffer> gS <plug>(lsp-workspace-symbol-search)
    nmap <buffer> gr <plug>(lsp-references)
    nmap <buffer> gi <plug>(lsp-implementation)
    nmap <buffer> gt <plug>(lsp-type-definition)
    nmap <buffer> <leader>rn <plug>(lsp-rename)
    nmap <buffer> [g <plug>(lsp-previous-diagnostic)
    nmap <buffer> ]g <plug>(lsp-next-diagnostic)
    nmap <buffer> K <plug>(lsp-hover)
    nmap <buffer> <Leader>ca <plug>(lsp-code-action)
    vmap <buffer> <Leader>ca :LspCodeAction<CR>
    nnoremap <buffer> <expr><c-f> lsp#scroll(+4)
    nnoremap <buffer> <expr><c-d> lsp#scroll(-4)

    let g:lsp_format_sync_timeout = 1000
    autocmd! BufWritePre *.rs,*.go call execute('LspDocumentFormatSync')
endfunction

augroup lsp_install
    au!
    autocmd User lsp_buffer_enabled call s:on_lsp_buffer_enabled()
augroup END

set foldmethod=expr
  \ foldexpr=lsp#ui#vim#folding#foldexpr()
  \ foldtext=lsp#ui#vim#folding#foldtext()
