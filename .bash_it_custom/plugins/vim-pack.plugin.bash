cite about-plugin
about-plugin 'vim plugins management'

export BUVIS_VIMPACKDIR=".vim/pack/plugins/opt/"

# add plugin
function packadd () {
    # full url to plugin's repo
    url=$1
    # extract the plugin name (part after last /)
    pname=$(expr "$url" : '.*/\(.*\)')
    cd $HOME
    /usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME submodule add --name $pname $url $BUVIS_VIMPACKDIR$pname
    cd -
}

# update plugins
function packup () {
    /usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME submodule update --remote --merge
}

# remove plugin
function packrm () {
    cd $HOME
    /usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME submodule deinit -f -- $BUVIS_VIMPACKDIR$1
    /usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME rm -f $BUVIS_VIMPACKDIR$1
    rm -rf $HOME/.buvis/modules/$1
    cd -
}
