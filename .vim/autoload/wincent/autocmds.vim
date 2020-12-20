let g:WincentColorColumnBufferNameBlacklist = ['__LanguageClient__']
let g:WincentColorColumnFileTypeBlacklist = ['command-t', 'diff', 'fugitiveblame', 'undotree', 'nerdtree', 'qf']
let g:WincentCursorlineBlacklist = ['command-t']
let g:WincentMkviewFiletypeBlacklist = ['diff', 'hgcommit', 'gitcommit']

function! wincent#autocmds#attempt_select_last_file() abort
  let l:previous=expand('#:t')
  if l:previous !=# ''
    call search('\v<' . l:previous . '>')
  endif
endfunction

function! wincent#autocmds#should_colorcolumn() abort
  if index(g:WincentColorColumnBufferNameBlacklist, bufname(bufnr('%'))) != -1
    return 0
  endif
  return index(g:WincentColorColumnFileTypeBlacklist, &filetype) == -1
endfunction

function! wincent#autocmds#should_cursorline() abort
  return index(g:WincentCursorlineBlacklist, &filetype) == -1
endfunction

function! s:get_spell_settings() abort
  return {
        \   'spell': &l:spell,
        \   'spellcapcheck': &l:spellcapcheck,
        \   'spellfile': &l:spellfile,
        \   'spelllang': &l:spelllang
        \ }
endfunction

function! s:set_spell_settings(settings) abort
  let &l:spell=a:settings.spell
  let &l:spellcapcheck=a:settings.spellcapcheck
  let &l:spellfile=a:settings.spellfile
  let &l:spelllang=a:settings.spelllang
endfunction

function! wincent#autocmds#blur_window() abort
  if wincent#autocmds#should_colorcolumn()
    let l:settings=s:get_spell_settings()
    "ownsyntax off
    set nolist
    if has('conceal')
      set conceallevel=0
    endif
    call s:set_spell_settings(l:settings)
  endif
endfunction

function! wincent#autocmds#focus_window() abort
  if wincent#autocmds#should_colorcolumn()
    if !empty(&ft)
      let l:settings=s:get_spell_settings()
      "ownsyntax on
      if &filetype != 'help'
        set list
      endif
      let l:conceal_exclusions=get(g:, 'indentLine_fileTypeExclude', [])
      if has('conceal') && index(l:conceal_exclusions, &ft) == -1
        set conceallevel=1
      endif
      call s:set_spell_settings(l:settings)
    endif
  endif
endfunction
