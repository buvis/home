cite about-plugin
about-plugin 'zetbrain tools'

# synchronize
function zsync () {
    cd $DOTFILES_ROOT/z/reference/notes
    git pull && git add . && git commit -m "sync" && git push
    cd -
}
