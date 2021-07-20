cite about-plugin
about-plugin 'zetbrain tools'

# synchronize
function zsync () {
    cd $HOME/z
    git pull && git add . && git commit -m "sync" && git push
    cd -
}
