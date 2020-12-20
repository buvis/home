" functions.vim
" functions definitions


"" Turn on spell-checking.
function! wincent#functions#spell() abort
  if has('syntax')
    setlocal spell
    setlocal spellfile=~/.vim/spell/en.utf-8.add
    setlocal spelllang=en
  endif
endfunction

" Switch to plaintext mode with: call wincent#functions#plaintext()
function! wincent#functions#plaintext() abort
  if has('conceal')
    let b:indentLine_ConcealOptionSet=1 " Don't let indentLine overwrite us.
    setlocal concealcursor=nc
  endif
  setlocal nolist
  setlocal textwidth=0
  setlocal wrap
  setlocal wrapmargin=0

  call wincent#functions#spell()

  " Break undo sequences into chunks (after punctuation); see: `:h i_CTRL-G_u`
  "
  " From:
  "
  "   https://twitter.com/vimgifs/status/913390282242232320
  "
  " Via:
  "
  "   https://github.com/ahmedelgabri/dotfiles/blob/f2b74f6cd4d/files/.vim/plugin/mappings.vim#L27-L33
  "
  inoremap <buffer> ! !<C-g>u
  inoremap <buffer> , ,<C-g>u
  inoremap <buffer> . .<C-g>u
  inoremap <buffer> : :<C-g>u
  inoremap <buffer> ; ;<C-g>u
  inoremap <bufer> ? ?<C-g>u

  nnoremap <buffer> j gj
  nnoremap <buffer> k gk

  " Ideally would keep 'list' set, and restrict 'listchars' to just show
  " whitespace errors, but 'listchars' is global and I don't want to go through
  " the hassle of saving and restoring.
  if has('autocmd')
    autocmd BufWinEnter <buffer> match Error /\s\+$/
    autocmd InsertEnter <buffer> match Error /\s\+\%#\@<!$/
    autocmd InsertLeave <buffer> match Error /\s\+$/
    autocmd BufWinLeave <buffer> call clearmatches()
  endif
endfunction
