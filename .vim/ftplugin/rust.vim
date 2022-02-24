" rust.vim
" rust specific settings


" syntax checker settings
let b:ale_linters = {'rust': ['analyzer','cargo']}
let b:ale_fixers = {'rust': [
    \ 'rustfmt',
    \ 'remove_trailing_lines',
    \ 'trim_whitespace',
    \ ] }

" use clippy for linting.
" INSTALL: rustup component add clippy-preview
let g:ale_rust_cargo_use_clippy = executable('cargo-clippy')
