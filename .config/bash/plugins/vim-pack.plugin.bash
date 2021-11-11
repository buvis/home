cite about-plugin
about-plugin 'vim plugins management'

export BUVIS_VIMPACKDIR=".vim/pack/plugins/opt/"

# add plugin
function packadd () {
    # full url to plugin's repo
    url=$1
    # extract the plugin name (part after last /)
    pname=$(expr "$url" : '.*/\(.*\)')
    cd $DOTFILES_ROOT
    /usr/bin/git --git-dir=$DOTFILES_ROOT/.buvis/ --work-tree=$DOTFILES_ROOT submodule add --name $pname $url $BUVIS_VIMPACKDIR$pname
    cd -
}

# update plugins
function packup () {
    /usr/bin/git --git-dir=$DOTFILES_ROOT/.buvis/ --work-tree=$DOTFILES_ROOT submodule update --remote --merge
}

# remove plugin
function packrm () {
    cd $DOTFILES_ROOT
    /usr/bin/git --git-dir=$DOTFILES_ROOT/.buvis/ --work-tree=$DOTFILES_ROOT submodule deinit -f -- $BUVIS_VIMPACKDIR$1
    /usr/bin/git --git-dir=$DOTFILES_ROOT/.buvis/ --work-tree=$DOTFILES_ROOT rm -f $BUVIS_VIMPACKDIR$1
    rm -rf $DOTFILES_ROOT/.buvis/modules/$1
    cd -
}
