#!/usr/bin/env bash
# Inspired by: https://www.atlassian.com/git/tutorials/dotfiles

REPO=$HOME/.buvis
rm -rf $REPO

cd $HOME

git clone --bare https://github.com/tbouska/buvis.git $REPO

function cfg {
    /usr/bin/git --git-dir=$REPO --work-tree=$HOME $@
}

cfg config status.showUntrackedFiles no

# Remove submodules
if [ -f "$HOME/.gitmodules" ]; then
    cfg config --file .gitmodules --get-regexp path | awk '{ print $2 }' | xargs -I{} rm -rf "{}"
fi

# Attempt checkout
cfg checkout 2>&1

if [[ $? = 0 ]]; then
    echo "Checked out config"
else
    echo "Backing up pre-existing dot files"
    mkdir -p $REPO/originals-backup
    cfg checkout 2>&1 | egrep "^\s+" | awk {'print $1'} | xargs -I{} echo "{}" >> $REPO/originals-backup/overwrites
    while read path; do
        parentdir="$(dirname "$path")"
        # Create missing directories in backup location
        if [[ -d "$HOME/$parentdir" ]]; then
            mkdir -p "$REPO/originals-backup/$parentdir"
        fi
        if [[ -e "$HOME/$path" ]]; then
            # Keep symlink's target, otherwise just move to backup location
            if [[ -L "$HOME/$path" ]]; then
                cp -a "$HOME/$path/" "$REPO/originals-backup/$path"
                unlink "$HOME/$path"
            else
                mv "$HOME/$path" "$REPO/originals-backup/$path"
            fi
            echo "$HOME/$path backed up to $REPO/originals-backup/$path"
        fi
    done <$REPO/originals-backup/overwrites
    cfg checkout
fi

if [[ $? = 0 ]]; then
    # Retrieve submodule's content
    cfg submodule update --init && cfg submodule update --remote --merge
    # Track master for pull/push
    cfg push -u origin master
    # Only keep README.md in remote (it is meant for public, but I don't need it on my machines)
    rm ~/README.md
    cfg update-index --skip-worktree README.md
fi
