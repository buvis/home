" visual.vim
" Visual mode mappings


" make folding shortcut easy to remember
vnoremap <Tab> za

" stay in visual mode when indenting
vnoremap < <gv
vnoremap > >gv

" copy selection to system clipboard
vnoremap Y "*y

" copy selection to system clipboard in WSL
if has("unix")
    if system('uname -r') =~ "Microsoft"
        func! GetSelectedText()
            normal gv"xy
            let result = getreg("x")
            return result
        endfunc
        vnoremap Y :call system('clip.exe', GetSelectedText())<CR>
    endif
endif
