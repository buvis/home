# Bob's Universal and Very Intelligent System

This repository contains more than my dotfiles, so I don't stick to the convention, and I'm not naming it "dotfiles".

Feel free to reuse anything, but proceed with caution.

If you find something I could be doing a better way, please drop me an email at tomas@buvis.net.
I always appreciate any opportunity to learn. Thank you!

## Prepare

### System independent steps

1. Install NerdFonts for Powerline from romkatv:
   - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Regular.ttf
   - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold.ttf
   - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Italic.ttf
   - https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold%20Italic.ttf
2. Install python and pip
3. Install libffi-dev (`brew install libffi` in macOS, `sudo apt install libffi-dev` in Linux, WSL)

### Additional system specific steps

#### macOS

1. Install all pending OS updates: About This Mac - Software Update...
2. Install xcode command line tools: `xcode-select --install`
3. Check that curl is installed: `command -v curl` (*it should come with the system but let's check anyway*)
4. Set the desired machine name following https://apple.stackexchange.com/questions/287760/set-the-hostname-computer-name-for-macos if booted for the first time
5. Restart

#### Windows

1. Configure git to keep line endings as they are: `git config --global core.autocrlf false`

#### WSL

1. Install prerequisites for python building: `sudo apt-get install -y build-essential checkinstall libreadline-gplv2-dev libncursesw5-dev libssl-dev libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev liblzma-dev`
2. Install node and npm: `sudo apt install nodejs npm`

## Install

### macOs (and possibly linux)
``` bash
curl -Ls https://tinyurl.com/buvis | /usr/bin/env bash
```

### Windows / WSL

Note: Install buvis to Windows host to share the configuration between host and WSL. Installation to WSL only would lack this benefit.

1. Copy `get-buvis.bat` from here
2. Run `get-buvis.bat` in `cmd`

## Post-install

Not all applications used by buvis can be configured using "dotfiles". You'll need to follow the manual instructions. Application-specific instructions are stored in [.config](./.config) directory.

### Use default configuration for ruff

#### macOS

Make symlink from `~/.config/ruff/ruff.toml` to `~/Library/Application Support/ruff/ruff.toml`

### Fix WSL issues
 
1. Link WSL home directory to Windows user's home
   1. Use buvis dotfiles inside WSL, add this to WSL's generated `~/.bashrc`:
   ```bash
   if [[ -f "<PATH_TO_WINDOWS_USER_HOME>/.profile" ]]; then
     source <PATH_TO_WINDOWS_USER_HOME>/.profile
   fi

   if [[ -f "<PATH_TO_WINDOWS_USER_HOME>/.bashrc" ]]; then
     source <PATH_TO_WINDOWS_USER_HOME>/.bashrc
   fi
   ```
   2. Create symlinks in vifm (`yy` source, `al` in destination)
      - `windows-home` from `/mnt/c/Users/<WINDOWS_USERNAME>`
      - `.default-python-packages`
      - `.tmux`
      - `.vifm`
      - `.vim`
      - `Downloads`
      - `bin`
      - `git`
      - `z`
      - `.tmux.conf`
      - `.vimrc`
2. Follow `20190805142816` in Zettelkasten to configure for corporate proxy
3. Fix files coloring in vifm
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
4. Fix asdf
   1. Make `utils.bash` executable: `chmod a-x <PATH_TO_WINDOWS_USER_HOME>/.asdf/lib/utils.bash`
   2. Make `commands` executable: `chmod -R a-x <PATH_TO_WINDOWS_USER_HOME>/.asdf/lib/commands`
   3. If asdf can't be used, check permissions with `ls -lla <PATH_TO_WINDOWS_USER_HOME>/.asdf/lib/commands` and if you see "?" everywhere, then run: `chmod -R a+rX *` in `<PATH_TO_WINDOWS_USER_HOME>`
5. Fix permissions to install npm packages globally: `sudo chown -R bob:bob /usr/local/`
6. Remember git credentials (run in $DOTFILES_ROOT): `cfg config credential.helper store`


### Install npm packages

1. `npm install -g npm-check write-good svelte-language-server`

### Install asdf managed python

1. Install asdf python plugin: `asdf plugin add python`
2. List available versions: `asdf list all python`
3. Build python with PyInstaller support: `env PYTHON_CONFIGURE_OPTS="--enable-shared" asdf install python <VERSION>`
4. Set global python version: `asdf global python <VERSION>`
5. Create links to default python packages (from `$HOME/.default-python-packages`): `asdf reshim python`

## Operations

### Update

1. Pull updates `cfgl` in `$DOTFILES_ROOT`
2. Stage updates: `cfgapa`
3. Commit updates with `<MESSAGE>`: `cfgm "<MESSAGE>"`
4. Push back to repository: `cfgp`

### Add default python package

1. Add package to `$HOME/.default-python-packages`
2. Install: `pip install -r $HOME/.default-python-packages`
