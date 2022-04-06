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

" send changes to git repository
function! buvis#functions#gitsend(...)
    if a:0 > 0 && a:1 != ""
        let commit_message = a:1
    else
        let commit_message = input("Enter commit message: ")
    endif

    if commit_message != ""
        execute "! git add . && git commit -m \"". commit_message ."\" && git pull && git push"
    else
        echo "Cancelled"
    endif
endfunction

function! buvis#functions#pymarkdownlint(buffer, lines) abort
    let l:output=[]

    for l:match in ale#util#GetMatches(a:lines, '\v([^:]+):(\d+):(\d+): (MD\d{3}): (.*)$')
        let l:result = ({
        \ 'lnum': l:match[2] + 0,
        \ 'code': l:match[4],
        \ 'text': l:match[5],
        \ 'type': 'W',
        \})

        if len(l:match[3]) > 0
            let l:result.col = (l:match[3] + 0)
        endif

        call add(l:output, l:result)
    endfor

    return l:output
endfunction
