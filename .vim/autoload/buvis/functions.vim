" functions.vim
" Functions for B.U.V.I.S.


" strip whitespace but keep history and cursor position unaffected
" source: http://vimcasts.org/episodes/tidying-whitespace/
function! buvis#functions#stripspaces()
    " save last search, and cursor position
    let _s=@/
    let l = line(".")
    let c = col(".")
    " do the magic:
    %s/\s\+$//e
    " restore previous search history, and cursor position
    let @/=_s
    call cursor(l, c)
endfunction
