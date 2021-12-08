@echo off
Rem Remove any previous installations
cd %HOME%
set REPO=%HOME%\.buvis
rmdir /Q /s %REPO%

Rem Clone as bare repository
git clone --bare https://github.com/tbouska/buvis.git %REPO%

Rem Don't list untracked files in git status
git --git-dir=%REPO% --work-tree=%HOME% config status.showUntrackedFiles no

Rem Avoid conflicts on checkout
echo Remove submodules listed in .gitmodules
pause > nul
echo Backup and remove conflicting files/folders (see repository at https://github.com/tbouska/buvis for the list of files)
pause > nul

Rem Checkout
git --git-dir=%REPO% --work-tree=%HOME% checkout

Rem Retrieve submodules' content
git --git-dir=%REPO% --work-tree=%HOME% submodule update --init
git --git-dir=%REPO% --work-tree=%HOME% submodule update --remote --merge

Rem Track master for pull/push
git --git-dir=%REPO% --work-tree=%HOME% push -u origin master

Rem Keep README.md and get-buvis.sh in remote only (it is meant for public, and I don't need it on my machines)
del %HOME%\README.md 
del %HOME%\get-buvis.sh
del %HOME%\get-buvis.bat
git --git-dir=%REPO% --work-tree=%HOME% update-index --skip-worktree README.md get-buvis.sh get-buvis.bat

Rem Print instructions to link alacritty config
echo Start cmd as Administrator and run:
echo.
echo 1. cd %APPDATA%
echo 2. mkdir alacritty
echo 3. mklink %APPDATA%\alacritty\alacritty.yml %HOME%\.config\alacritty\alacritty-windows.yml
echo 4. mklink %APPDATA%\alacritty\alacritty.info %HOME%\.config\alacritty\alacritty.info
pause > nul
