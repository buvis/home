" autocmds.vim
" Autocommands


" dim on focus out, taken from https://github.com/wincent/wincent
if has('autocmd')
  function! s:WincentAutocmds()
    augroup WincentAutocmds
      autocmd!

      " Make current window more obvious by turning off/adjusting some
      " features in non-current windows.
      if exists('+winhighlight')
        autocmd BufEnter,FocusGained,VimEnter,WinEnter * set winhighlight=
        autocmd FocusLost,WinLeave * set winhighlight=CursorLineNr:LineNr,EndOfBuffer:ColorColumn,IncSearch:ColorColumn,Normal:ColorColumn,NormalNC:ColorColumn,SignColumn:ColorColumn
        if exists('+colorcolumn')
          autocmd BufEnter,FocusGained,VimEnter,WinEnter * let &l:colorcolumn='+' . join(range(0, 254), ',+')
        endif
      elseif exists('+colorcolumn')
        autocmd BufEnter,FocusGained,VimEnter,WinEnter * let &l:colorcolumn='+' . join(range(0, 254), ',+')
        autocmd FocusLost,WinLeave * let &l:colorcolumn=join(range(1, 255), ',')
      endif
      autocmd InsertLeave,VimEnter,WinEnter * setlocal cursorline
      autocmd InsertEnter,WinLeave * setlocal nocursorline
      autocmd BufEnter,FocusGained,VimEnter,WinEnter * call wincent#autocmds#focus_window()
      autocmd FocusLost,WinLeave * call wincent#autocmds#blur_window()

    augroup END
  endfunction
  call s:WincentAutocmds()
endif
