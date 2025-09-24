
# PowerShell profile
# don't forget to execute Set-ExecutionPolicy -Scope CurrentUser RemoteSigned for it to work
# modules installation requires: Install-Module -Name PowerShellGet -Force
# each module needs to be installed first: Install-Module <module_name>
#
# https://github.com/dahlbyk/posh-git
Import-Module posh-git
# https://github.com/gluons/powershell-git-aliases
Import-Module git-aliases -DisableNameChecking
# https://github.com/PowerShell/PSReadLine
Import-Module PSReadLine

oh-my-posh --init --shell pwsh --config "$env:POSH_THEMES_PATH\powerlevel10k_rainbow.omp.json" | Invoke-Expression

# Allow local scripts execution without .\
$env:PATH =$env:PATH+";."

# Use buvis scripts
$env:PATH =$env:PATH+";"+$env:HOME+"\scripts\bin"

# Use direnv
# Invoke-Expression "$(direnv hook pwsh)"

# Use mise
mise activate pwsh | Out-String | Invoke-Expression

# "Windows PowerShell" does not support the `e special character sequence for Escape, so we use a variable $e for this.
$e = [char]27

function global:PromptWriteErrorInfo() {
    if ($global:gitpromptvalues.dollarquestion) {
        "$e[0;32mv$e[0m"
    }
    else {
        "$e[0;31mx$e[0m"
    }
}

$gitpromptsettings.defaultpromptabbreviatehomedirectory      = $true

$gitpromptsettings.defaultpromptpath.foregroundcolor         = 0xC4A000

$gitpromptsettings.defaultpromptprefix.text                  = '$(PromptWriteErrorInfo) '

$username = $env:USERNAME
$hostname = $env:COMPUTERNAME.tolower()

$gitpromptsettings.defaultpromptwritestatusfirst             = $false
$gitpromptsettings.defaultpromptbeforesuffix.text            = "`n$e[0m$e[38;2;140;206;250m$username$e[1;97m@$e[0m$e[38;2;140;206;250m$hostname "
$gitpromptsettings.defaultpromptsuffix.foregroundcolor       = 0xDC143C

$gitpromptsettings.windowtitle = $null
$host.ui.rawui.windowtitle = $hostname


set-psreadlineoption     -editmode emacs
set-psreadlinekeyhandler -key tab       -function complete
set-psreadlinekeyhandler -key uparrow   -function historysearchbackward
set-psreadlinekeyhandler -key downarrow -function historysearchforward

Set-PSReadLineOption -Colors @{
  Command            = '#6c71c4'
  Number             = '#657b83'
  Member             = '#657b83'
  Operator           = '#657b83'
  Type               = '#657b83'
  Variable           = '#859900'
  Parameter          = '#859900'
  ContinuationPrompt = '#657b83'
  InlinePrediction   = '#657b83'
  Default            = '#657b83'
}
Set-PSReadlineOption -BellStyle None
