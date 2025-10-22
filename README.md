# Bob's Universal and Very Intelligent System

This repository contains more than my dotfiles, so I don't stick to the convention, and I'm not naming it "dotfiles".

Feel free to reuse anything, but proceed with caution.

If you find something I could be doing a better way, please drop me an email at <tomas@buvis.net>.
I always appreciate any opportunity to learn. Thank you!

## Prepare

### System independent steps

1. Install NerdFonts for Powerline from romkatv:
   - <https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Regular.ttf>
   - <https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold.ttf>
   - <https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Italic.ttf>
   - <https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold%20Italic.ttf>
2. Install python and pip
3. Install node
4. Install lazygit
   - MacOS: `brew install jesseduffield/lazygit/lazygit`
   - Windows: `scoop bucket add extras; scoop install lazygit`
5. Install libffi-dev (`brew install libffi` in macOS, `sudo apt install libffi-dev` in Linux, WSL)

### Additional system-specific steps

#### macOS

1. Install all pending OS updates: About This Mac - Software Update...
2. Install xcode command line tools: `xcode-select --install`
3. Check that curl is installed: `command -v curl` (_it should come with the system but let's check anyway_)
4. Set the desired machine name following <https://apple.stackexchange.com/questions/287760/set-the-hostname-computer-name-for-macos> if booted for the first time
5. Restart

#### Windows

1. Configure git to keep line endings as they are: `git config --global core.autocrlf false`
2. Create commonly used ENV variables pointing to home:
    - `[Environment]::SetEnvironmentVariable("HOME", "$env:USERPROFILE", [System.EnvironmentVariableTarget]::User)`
    - `[Environment]::SetEnvironmentVariable("XDG_CONFIG_HOME", "$env:USERPROFILE\.config", [System.EnvironmentVariableTarget]::User)`
3. Install useful apps: `scoop install ag fd fzf neovim ripgrep vifm wget wezterm`

#### WSL

Currently not using, so I can't provide specific instructions.

## Install

### macOS, WSL, and potentially any Linux distro

```bash
curl -Ls https://tinyurl.com/buvis | /usr/bin/env bash
```

### Windows

1. Copy `get-buvis.bat` from here
2. Run `get-buvis.bat` in `cmd`

## Post-install

Not all applications used by buvis can be configured using "dotfiles". You'll need to follow the manual instructions. Application-specific instructions are stored in [.config](./.config) directory.

### Automate scripts' dependencies updates

Create `post-merge` hook in `.buvis/modules/scripts/.git/hooks` according to [buvis scripts update automation instructions](https://github.com/buvis/scripts?tab=readme-ov-file#update)

### Configure git

1. Go to dotfiles root: `cd $DOTFILES_ROOT`
2. Store credentials: `cfg config credential.helper store`
3. Honor global ignores: `git config --global core.excludesfile ~/.gitignore_global`

### Windows

#### PATH

Add `~\scripts\bin` to PATH.

#### PowerShell profile

Make symlink from `~/.config/powershell/Microsoft.PowerShell_profile.ps1` to `PowerShell` folder in `shell:DocumentsLibrary` folder.

#### Use default configuration for ruff

I don't know how, will add later.

#### LazyGit

Make symlink from `~/.config/lazygit/config.yml` to `%LOCALAPPDATA%\lazygit\config.yml`

### macOS

#### Use default configuration for ruff

Make symlink from `~/.config/ruff/pyproject.toml` to `~/Library/Application Support/ruff/pyproject.toml`

#### LazyGit

Make symlink from `~/.config/lazygit/config.yml` to `~/Library/Application Support/lazygit/config.yml`

### WSL

1. Create symlinks in vifm (`yy` source, `al` in destination)
   - `windows-home` from `/mnt/c/Users/<WINDOWS_USERNAME>`
   - `Downloads` from `/mnt/c/Users/<WINDOWS_USERNAME>/Downloads`
   - `onedrive-company` from `/mnt/c/Users/<WINDOWS_USERNAME>/<OneDrive - company>`
   - `onedrive-private` from `/mnt/c/Users/<WINDOWS_USERNAME>/<OneDrive - private>`
   - `z` from `/mnt/c/Users/<WINDOWS_USERNAME>/<OneDrive - private>/z`
2. Fix files coloring in vifm
   1. Add filesystem configuration to `/etc/wsl.conf`

      ```ini
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

### Install developer tools

Run `mise install` while at $HOME.

### Get git repositories

1. Create directory for git: `mkdir -p $HOME/git/src`
2. Clone repositories you need
3. Repeat for each repository: add repository to gita: `gita add .`

## Operations

### Update

#### macOS, WSL, and potentially any Linux distro

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
