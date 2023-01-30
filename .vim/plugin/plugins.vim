" plugins.vim
" plugin settings


" ctrlp
"   activation shortcut
let g:ctrlp_map = '-'
"   ignore VCS and /pack which contains vim plugins
let g:ctrlp_custom_ignore = {
  \ 'dir':  '\v([\/]\.(git|hg|svn)|\/pack)$',
  \ 'file': '\v\.(exe|so|dll)$',
  \ 'link': 'some_bad_symbolic_links' }
"   ignore files specified in .gitignore
let g:ctrlp_user_command = ['.git', 'cd %s && git ls-files -co --exclude-standard']

" markdown-preview.nvim
"   launch shortcut
nmap <C-m> <Plug>MarkdownPreview

" fzf
"   set layout
"   ATTENTION: bat needs to be configured to use Solarized (dark) theme,
"   otherwise the text in popup will be unreadable
"   1. ''bat --config-file''
"   2. add --theme="Solarized (dark)" in it
let g:fzf_layout = { 'window': { 'width': 0.9, 'height': 0.6  }  }

" vimwiki
let g:vimwiki_list = [
  \  {'path':'~/z/reference/notes/',
  \   'ext':'.md',
  \   'syntax':'markdown'}]
let g:vimwiki_conceallevel = 0
let g:vimwiki_markdown_link_ext = 1

" vim-zettel
function! s:insert_id()
  if exists("g:zettel_current_id")
    return g:zettel_current_id
  else
    return "unnamed"
  endif
endfunction

function! s:get_title()
    return input("Enter title: ")
endfunction

let g:zettel_options = [{"template" : "../zettel.tpl", "disable_front_matter": 1,
  \  "front_matter" : [
      \ [ "id", function("s:insert_id")],
      \ [ "title", function("s:get_title")],
      \ [ "type", "wiki-article" ],
      \ [ "tags", "[]" ]]
  \ }]

let g:zettel_format = "%Y%m%d%H%M%S"
let g:zettel_date_format = "%Y-%m-%dT%H:%M:%S%z"

" ALE
let g:ale_virtualtext_cursor = 0
let g:ale_echo_msg_format = '[%linter%] %s [%severity%]'
let g:ale_fix_on_save = 1
let g:ale_sign_error = '✘'
let g:ale_sign_warning = '⚠'

" pear-tree
" avoid conflict with asyncomplete choice confirmation by ENTER
let g:pear_tree_map_special_keys = 0

" vim-rooter
let g:rooter_patterns = ["=src", ".git", "Makefile", "README.md", "cli.py"]
