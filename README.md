# Bob's Universal and Very Intelligent System

This repository contains more than my dotfiles, so I don't stick to the convention, and I'm not naming it "dotfiles".

Feel free to reuse anything, but proceed with caution.

If you find something I could be doing a better way, please drop me an email at tomas@buvis.net.
I always appreciate any opportunity to learn. Thank you!

## Prepare

### macOS

1. Install all pending OS updates: About This Mac - Software Update...
2. Install xcode command line tools: `xcode-select --install`
3. Check that curl is installed: `command -v curl` (*it should come with the system but let's check anyway*)
4. Set the desired machine name following https://apple.stackexchange.com/questions/287760/set-the-hostname-computer-name-for-macos if booted for the first time
5. Install NerdFonts for Powerline from romkatv:
    * https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Regular.ttf
    * https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold.ttf
    * https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Italic.ttf
    * https://github.com/romkatv/powerlevel10k-media/raw/master/MesloLGS%20NF%20Bold%20Italic.ttf
6. Restart

## Install

1. Shared core: `curl -Ls https://tinyurl.com/get-buvis | /usr/bin/env bash`
2. TODO: OS and/or machine specific setup scripts

### WSL
WSL home directory is different from Windows user's home. To use buvis dotfiles inside WSL you need to add
```bash
if [[ -f "<PATH_TO_WINDOWS_USER_HOME>/.profile" ]]; then
  source <PATH_TO_WINDOWS_USER_HOME>/.profile
fi

if [[ -f "<PATH_TO_WINDOWS_USER_HOME>/.bashrc" ]]; then
  source <PATH_TO_WINDOWS_USER_HOME>/.bashrc
fi
```
to WSL's generated `~/.bashrc`.
    
## Configure

Not all applications used by buvis can be configured using "dotfiles". You'll need to follow the manual instructions. Application-specific instructions are stored in [.config](./.config) directory.
