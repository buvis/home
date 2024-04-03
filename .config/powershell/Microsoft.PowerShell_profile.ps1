# PowerShell profile
# don't forget to execute Set-ExecutionPolicy -Scope CurrentUser RemoteSigned for it to work
# https://github.com/dahlbyk/posh-git
Import-Module posh-git
# https://github.com/JanDeDobbeleer/oh-my-posh3
Import-Module oh-my-posh
# https://github.com/gluons/powershell-git-aliases
Import-Module git-aliases -DisableNameChecking
Set-Theme Paradox

Set-Alias -Name doo -Value C:\Users\tbouska\.local\bin\doogat\doo\doo.exe

function cdg {cd ~/git/src/gitlab.com/doogat}
function bb {doo create bookmark --edit}
function cc {doo create contact --edit}
function mm {doo create minutes --edit}
function pp {doo create loop --edit}
function qq {doo create quote --edit}
function ss {doo create snippet --edit}
function ww {doo create wiki-article --edit}
