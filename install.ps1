# Inspired by: https://www.atlassian.com/git/tutorials/dotfiles

function info { Write-Host ($args -join ' ') }
function error { Write-Host "error: $($args -join ' ')"; exit 1 }

$Repo = Join-Path $HOME ".buvis"
$Backup = Join-Path $Repo "originals-backup"

# --- Phase 1: Bootstrap system tools ---

# Set HOME and XDG_CONFIG_HOME if not already set
if (-not $env:HOME) {
    [Environment]::SetEnvironmentVariable("HOME", $env:USERPROFILE, [System.EnvironmentVariableTarget]::User)
    $env:HOME = $env:USERPROFILE
}
if (-not $env:XDG_CONFIG_HOME) {
    $xdg = Join-Path $env:USERPROFILE ".config"
    [Environment]::SetEnvironmentVariable("XDG_CONFIG_HOME", $xdg, [System.EnvironmentVariableTarget]::User)
    $env:XDG_CONFIG_HOME = $xdg
}

# Keep line endings as-is
$autocrlf = git config --global core.autocrlf 2>$null
if ($autocrlf -ne "false") {
    git config --global core.autocrlf false
}

# Install Scoop if missing
if (-not (Get-Command scoop -ErrorAction SilentlyContinue)) {
    info "Installing Scoop..."
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
    Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
}

# Add buckets and install tools
scoop bucket add extras 2>$null
scoop bucket add nerd-fonts 2>$null

$scoopPackages = @("git", "lazygit", "fd", "fzf", "neovim", "ripgrep", "vifm", "wget", "wezterm", "mise", "ag")
foreach ($pkg in $scoopPackages) {
    if (-not (Get-Command $pkg -ErrorAction SilentlyContinue)) {
        info "Installing $pkg..."
        scoop install $pkg
    }
}

# Install NerdFont
$fontInstalled = scoop list 2>$null | Select-String "Meslo-NF"
if (-not $fontInstalled) {
    info "Installing MesloLGS NerdFont..."
    scoop install nerd-fonts/Meslo-NF
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    error "git is required"
}

function cfg {
    & git --git-dir="$Repo" --work-tree="$HOME" @args
}

Set-Location $HOME

# --- Phase 2: Dotfiles checkout ---

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

# --- Phase 3: Package installation ---

if (Get-Command mise -ErrorAction SilentlyContinue) {
    info "Installing mise-managed tools..."
    mise install
    if (Get-Command sysup -ErrorAction SilentlyContinue) {
        sysup nvim
    }
}

# --- Phase 4: Post-checkout configuration ---

cfg config credential.helper store
git config --global core.excludesfile (Join-Path $HOME ".gitignore_global")

$gitSrc = Join-Path $HOME "git/src"
if (-not (Test-Path $gitSrc)) {
    New-Item -ItemType Directory -Force -Path $gitSrc | Out-Null
}

# Symlink lazygit config to expected Windows location
$lazygitSrc = Join-Path $HOME ".config/lazygit/config.yml"
$lazygitDst = Join-Path $env:LOCALAPPDATA "lazygit/config.yml"
if ((Test-Path $lazygitSrc) -and -not (Test-Path $lazygitDst)) {
    $lazygitDstDir = Split-Path $lazygitDst -Parent
    New-Item -ItemType Directory -Force -Path $lazygitDstDir | Out-Null
    New-Item -ItemType SymbolicLink -Path $lazygitDst -Target $lazygitSrc | Out-Null
    info "Linked $lazygitDst"
}

# Symlink PowerShell profile
$profileSrc = Join-Path $HOME ".config/powershell/profile.ps1"
if ((Test-Path $profileSrc) -and $PROFILE -and -not (Test-Path $PROFILE)) {
    $profileDir = Split-Path $PROFILE -Parent
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
    New-Item -ItemType SymbolicLink -Path $PROFILE -Target $profileSrc | Out-Null
    info "Linked PowerShell profile to $PROFILE"
}

# Clone repositories listed in gita config
$gitaCsv = Join-Path $HOME ".config/gita/repos.csv"
if (Test-Path $gitaCsv) {
    info "Cloning tracked repositories..."
    foreach ($line in Get-Content $gitaCsv) {
        $parts = $line -split ','
        $repoPath = $parts[0]
        $repoName = $parts[1]
        if (Test-Path $repoPath) { continue }

        # Derive clone URL from path: .../git/src/github.com/owner/repo -> git@github.com:owner/repo.git
        $urlPart = $repoPath -replace '.*[/\\]git[/\\]src[/\\]', ''
        $segments = $urlPart -split '[/\\]', 2
        $cloneUrl = "git@$($segments[0]):$($segments[1]).git"

        $parentDir = Split-Path $repoPath -Parent
        New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
        git clone $cloneUrl $repoPath 2>$null
        if ($LASTEXITCODE -eq 0) {
            info "Cloned $repoName"
        } else {
            info "warning: failed to clone $repoName ($cloneUrl), skipping"
        }
    }
}

# --- Phase 5: Additional tools ---

# Install Claude CLI
info "Installing Claude CLI..."
try {
    Invoke-Expression (Invoke-RestMethod -Uri "https://claude.ai/install.ps1")
    info "Claude CLI installed"
} catch {
    info "warning: Claude CLI installation failed: $_"
    info "Continuing with dotfiles setup"
}

# Private configs (cellar)
$Cellar = Join-Path $HOME "git/src/github.com/buvis/cellar"
if (Test-Path $Cellar) {
    & (Join-Path $Cellar "setup.ps1")
} else {
    git clone git@github.com:buvis/cellar.git $Cellar 2>$null
    if ($LASTEXITCODE -eq 0) {
        & (Join-Path $Cellar "setup.ps1")
    } else {
        info "Skipping private configs (no access to cellar)"
    }
}
