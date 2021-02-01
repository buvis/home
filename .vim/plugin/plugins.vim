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

" vim-gnupg
"   prefer symmetric encryption
let g:GPGPreferSymmetric = 1
