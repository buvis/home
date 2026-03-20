#!/usr/bin/env pwsh
# Inspired by: https://www.atlassian.com/git/tutorials/dotfiles

function info { Write-Host ($args -join ' ') }
function error { Write-Host "error: $($args -join ' ')"; exit 1 }

$Repo = Join-Path $HOME ".buvis"
$Backup = Join-Path $Repo "originals-backup"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    error "git is required"
}

function cfg {
    & git --git-dir="$Repo" --work-tree="$HOME" @args
}

Set-Location $HOME

# Clone or fetch
if (Test-Path $Repo) {
    info "Updating existing repo"
    cfg config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
    cfg fetch origin
} else {
    git clone --bare https://github.com/buvis/home.git $Repo
    cfg config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
    cfg fetch origin
}

cfg config status.showUntrackedFiles no

# Identify this machine in commits
$hostname = $env:COMPUTERNAME
if (-not $hostname) { $hostname = [System.Net.Dns]::GetHostName() }
cfg config user.name $hostname
cfg config user.email "$hostname@buvis.net"

# Remove leftover submodule directories from previous installs
$gitmodules = Join-Path $HOME ".gitmodules"
if (Test-Path $gitmodules) {
    $paths = cfg config --file .gitmodules --get-regexp path 2>$null
    if ($paths) {
        foreach ($line in $paths) {
            $p = ($line -split '\s+', 2)[1]
            $full = Join-Path $HOME $p
            if (Test-Path $full) {
                Remove-Item -Recurse -Force $full
            }
        }
    }
}

# Checkout, backing up conflicting files if needed
cfg checkout 2>$null
if ($LASTEXITCODE -eq 0) {
    info "Checked out config"
} else {
    info "Backing up pre-existing dot files"
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null

    # Re-run checkout to capture conflict list from stderr
    $output = (cfg checkout 2>&1) | Out-String
    $conflicts = $output -split "`n" |
        Where-Object { $_ -match '^\s+\S' } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne '' }

    foreach ($path in $conflicts) {
        $src = Join-Path $HOME $path
        if (-not (Test-Path $src)) { continue }

        $dst = Join-Path $Backup $path
        $dstDir = Split-Path $dst -Parent
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

        $item = Get-Item $src -Force
        if ($item.LinkType) {
            Copy-Item $src $dst
            Remove-Item $src -Force
        } else {
            Move-Item $src $dst -Force
        }
        info "Backed up $path"
    }

    cfg checkout
    if ($LASTEXITCODE -ne 0) { error "checkout failed after backup" }
}

# Set up remote tracking
cfg branch -u origin/master master 2>$null

# Retrieve submodule content
cfg submodule update --init
cfg submodule update --remote --merge

if (Get-Command mise -ErrorAction SilentlyContinue) {
    mise install
}
