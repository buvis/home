m

This repository contains more than my dotfiles, so I don't stick to the convention, and I'm not naming it "dotfiles".

Feel free to reuse anything, but proceed with caution.

If you find something I could be doing a better way, please drop me an email at tomas@buvis.net.
I always appreciate any opportunity to learn. Thank you!

## Prepare

### System independent steps

1. Install NerdFonts for Powerline from romkatv:
    - manually
        - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Regular.ttf
        - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold.ttf
        - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Italic.ttf
        - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold%20Italic.ttf
    - MacOS (homebrew)
        - `brew tap homebrew/cask-fonts`
        - `brew install font-meslo-lg-nerd-font`
2. Install python and pip
3. Install libffi-dev (`brew install libffi` in macOS, `sudo apt install libffi-dev` in Linux, WSL)

### Additional system specific steps

#### MacOS

1. Install all pending OS updates: About This Mac - Software Update...
2. Install xcode command line tools: `xcode-select --install`
3. Check that curl is installed: `command -v curl` (*it should come with the system but let's check anyway*)
4. Set the desired machine name following https://apple.stackexchange.com/questions/287760/set-the-hostname-computer-name-for-macos if booted for the first time
5. Restart

#### Windows

1. Configure git to keep line endings as they are: `git config --global core.autocrlf false`

#### WSL

1. Follow `20190805142816` in Zettelkasten to fix network issues in corporate environment (excuse me, I can't publish this, as it contains my employer's sensitive information; it is about getting WSL network work by using [wsl-vpnkit](https://github.com/sakai135/wsl-vpnkit) and using proxy forwarder on Windows host)
2. Update the system: `sudo apt update && sudo apt upgrade`
3. Install packages used by BUVIS: `sudo apt-get install -y build-essential checkinstall direnv libreadline-dev libncursesw5-dev libssl-dev libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev liblzma-dev nodejs npm vifm`

## Install

### MacOS, WSL, and potentially any Linux distro
``` bash
curl -Ls https://tinyurl.com/buvis | /usr/bin/env bash
```

### Windows

1. Copy `get-buvis.bat` from here
2. Run `get-buvis.bat` in `cmd`

## Post-install

Not all applications used by buvis can be configured using "dotfiles". You'll need to follow the manual instructions. Application-specific instructions are stored in [.config](./.config) directory.

### Remember git credentials

1. Go to dotfiles root: `cd $DOTFILES_ROOT`
2. Configure git to store credentials: `cfg config credential.helper store`

### Install tmux plugins

When in tmux, press `<tmux-prefix>+I`.

### Use default configuration for ruff

#### MacOS

Make symlink from `~/.config/ruff/ruff.toml` to `~/Library/Application Support/ruff/ruff.toml`

### WSL
 
1. Create symlinks in vifm (`yy` source, `al` in destination)
   - `windows-home` from `/mnt/c/Users/<WINDOWS_USERNAME>`
   - `Downloads` from `/mnt/c/Users/<WINDOWS_USERNAME>/Downloads`
   - `onedrive-company` from `/mnt/c/Users/<WINDOWS_USERNAME>/<OneDrive - company>`
   - `onedrive-private` from `/mnt/c/Users/<WINDOWS_USERNAME>/<OneDrive - private>`
   - `z` from `/mnt/c/Users/<WINDOWS_USERNAME>/<OneDrive - private>/z`
2. Fix files coloring in vifm
   1. Add filesystem configuration to `/etc/wsl.conf`
      ``` ini
      [automount]
      enabled = true
      options = "metadata,uid=1000,gid=1000,umask=0022,fmask=11,case=off"
      mountFsTab = false
      crossDistro = true
      
      [filesystem]
      umask = 0022
      ```
   2. Restart WSL: run `wsl --terminate Ubuntu` in `cmd`, then start WSL
   3. Run `chmod -R a-x+X,u-x+rwX,go-wx+rX *` in directory where you want to fix the file coloring in vifm
3. Fix permissions to install npm packages globally: `npm config set prefix '~/.local/'`
4. Fix locale: `sudo tic -xe alacritty,alacritty-direct ~/.config/alacritty/alacritty.info`
5. Use WSL specific configuration for some tools: `vim $HOME/.bashrc-wsl`, add
```
export P_PROPERTIES_FILE="/home/bob/.pdata-wsl.properties"
export GITA_PROJECT_HOME="/home/bob/.config/wsl/"
```
6. Let VS Code from Windows host use WSL
   1. Install [WSL Extenstion](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl)
   2. Add VS Code to WSL's path: `echo 'export PATH=$PATH:/mnt/c/Users/tbouska/.local/bin/vscode/bin' >> ~/.bashrc-wsl`

### Install tools

Run `asdf install`.

### Get git repositories

1. Create directory for git: `mkdir -p $HOME/git/src`
2. Clone repositories you need
3. Repeat for each repository: add repository to gita: `gita add .`

## Operations

### Update

#### MacOS, WSL, and potentially any Linux distro

1. Open terminal
2. Go to user's home: `cd $HOME`
3. Pull updates `cfgl`
4. Stage updates: `cfgapa`
5. Commit updates with `<MESSAGE>`: `cfgm "<MESSAGE>"`
6. Push back to repository: `cfgp`

#### Windows

1. Run `cmd`
2. Go to user's home: `cd %userprofile%`
3. Pull updates `cfgl.bat`
4. Stage updates: `cfgapa.bat`
5. Commit updates with `<MESSAGE>`: `cfgm.bat "<MESSAGE>"`
6. Push back to repository: `cfgp.bat`

### Add default python package

1. Add package to `$HOME/.default-python-packages`
2. Install: `pip install -r $HOME/.default-python-packages`
