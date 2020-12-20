# PowerShell profile
# don't forget to execute Set-ExecutionPolicy -Scope CurrentUser RemoteSigned for it to work
# https://github.com/dahlbyk/posh-git
Import-Module posh-git
# https://github.com/JanDeDobbeleer/oh-my-posh3
Import-Module oh-my-posh
# https://github.com/gluons/powershell-git-aliases
Import-Module git-aliases -DisableNameChecking
Set-Theme Paradox

function cdg {cd ~/git/src/gitlab.com/doogat}
function bb {doo create bookmark}
function cc {doo create contact}
function mm {doo create minutes}
function pp {doo create loop}
function qq {doo create quote}
function ss {doo create snippet}
function ww {doo create wiki-article}
