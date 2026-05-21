################################################################################
#                    Dagdi CLI - Interactive Update Script (Windows)
#
# This script helps you update an existing Dagdi CLI installation.
# It supports git-based updates and manual (downloaded) updates.
#
# Usage: powershell -ExecutionPolicy Bypass -File update.ps1
################################################################################

$ErrorActionPreference = "Stop"

$BackupExcludeDirs = @(".git", "venv", ".venv", "__pycache__", "*.egg-info", ".eggs",
                        "node_modules", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache")
$UserDataDirs = @("config", ".dagdi")

function Write-Header($Message) {
    Write-Host ""
    Write-Host "================================" -ForegroundColor Blue
    Write-Host $Message -ForegroundColor Blue
    Write-Host "================================" -ForegroundColor Blue
    Write-Host ""
}

function Write-Success($Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Err($Message)     { Write-Host "[X]  $Message" -ForegroundColor Red }
function Write-Warn($Message)    { Write-Host "[!]  $Message" -ForegroundColor Yellow }
function Write-Info($Message)    { Write-Host "[i]  $Message" -ForegroundColor Cyan }

function Test-CommandExists($Name) {
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

# ---------------------------------------------------------------------------
# Locate existing installation
# ---------------------------------------------------------------------------
function Find-Installation {
    Write-Header "Dagdi CLI - Update Script (Windows)"

    Write-Host "This script will update your existing Dagdi CLI installation."
    Write-Host ""

    # Check current directory
    if ((Test-Path "pyproject.toml") -and (Select-String -Path "pyproject.toml" -Pattern 'name.*=.*"dagdi-cli"' -Quiet)) {
        Write-Info "Detected Dagdi CLI project in current directory: $(Get-Location)"
        $use = Read-Host "Use this location? (y/n)"
        if ($use -eq "y") {
            return (Get-Location).Path
        }
    }

    $installPath = Read-Host "Enter the path to your existing Dagdi CLI installation"
    $installPath = $installPath.Trim('"').Trim("'")

    if (-not (Test-Path $installPath -PathType Container)) {
        Write-Err "Directory not found: $installPath"
        exit 1
    }

    if (-not (Test-Path (Join-Path $installPath "pyproject.toml"))) {
        Write-Err "Not a valid Dagdi project (no pyproject.toml found in $installPath)"
        exit 1
    }

    $pyproject = Join-Path $installPath "pyproject.toml"
    if (-not (Select-String -Path $pyproject -Pattern 'name.*=.*"dagdi-cli"' -Quiet)) {
        Write-Err "pyproject.toml exists but does not appear to be dagdi-cli."
        exit 1
    }

    Write-Success "Found Dagdi CLI at: $installPath"
    return $installPath
}

# ---------------------------------------------------------------------------
# Show current version info
# ---------------------------------------------------------------------------
function Show-CurrentVersion($DagdiDir) {
    Write-Host ""

    $initFile = Join-Path $DagdiDir "src\dagdi\__init__.py"
    if (Test-Path $initFile) {
        $match = Select-String -Path $initFile -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match) {
            Write-Info "Current installed version: $($match.Matches.Groups[1].Value)"
        }
    }

    $gitDir = Join-Path $DagdiDir ".git"
    if (Test-Path $gitDir) {
        $commit = git -C $DagdiDir log --oneline -1 2>$null
        $branch = git -C $DagdiDir branch --show-current 2>$null
        if ($branch) { Write-Info "Current branch: $branch" }
        if ($commit) { Write-Info "Current commit: $commit" }
    }

    Write-Host ""
}

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
function New-Backup($DagdiDir) {
    Write-Header "Backup"

    $do = Read-Host "Do you want to create a backup of the current installation? (y/n)"
    if ($do -ne "y") {
        Write-Warn "Skipping backup."
        return
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = "$DagdiDir-backup-$timestamp"

    Write-Info "Creating backup at: $backupDir"

    # Copy everything first
    Copy-Item -Path $DagdiDir -Destination $backupDir -Recurse -Force

    # Remove excluded directories from backup
    foreach ($pattern in $BackupExcludeDirs) {
        Get-ChildItem -Path $backupDir -Directory -Recurse -Filter $pattern -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Success "Backup created at: $backupDir"
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Git-based update
# ---------------------------------------------------------------------------
function Update-ViaGit($DagdiDir) {
    Write-Header "Update via Git"

    Push-Location $DagdiDir

    try {
        # Check for uncommitted changes
        $status = git status --porcelain 2>$null
        if ($status) {
            Write-Warn "You have uncommitted changes:"
            git status --short
            Write-Host ""
            $cont = Read-Host "Continue anyway? Changes may conflict with the update. (y/n)"
            if ($cont -ne "y") {
                Write-Info "Update cancelled. Please commit or stash your changes first."
                exit 0
            }
        }

        # Current branch
        $currentBranch = git branch --show-current 2>$null
        if (-not $currentBranch) { $currentBranch = "main" }

        Write-Host "Current branch: $currentBranch"
        $targetBranch = Read-Host "Branch to update from (default: $currentBranch)"
        if ([string]::IsNullOrWhiteSpace($targetBranch)) { $targetBranch = $currentBranch }

        # Fetch
        Write-Info "Fetching latest changes..."
        git fetch origin $targetBranch
        Write-Host ""

        # Check incoming commits
        $incoming = git log --oneline "HEAD..origin/$targetBranch" 2>$null
        if (-not $incoming) {
            Write-Success "Already up to date! No new commits."
            Write-Host ""
            $reinstall = Read-Host "Reinstall dependencies anyway? (y/n)"
            if ($reinstall -ne "y") {
                Write-Info "Nothing to do."
                exit 0
            }
            return
        }

        Write-Host "Incoming changes:" -ForegroundColor Cyan
        Write-Host $incoming
        Write-Host ""

        $filesChanged = git diff --stat "HEAD..origin/$targetBranch" 2>$null
        Write-Host "Files changed:" -ForegroundColor Cyan
        Write-Host $filesChanged
        Write-Host ""

        $apply = Read-Host "Apply these changes? (y/n)"
        if ($apply -ne "y") {
            Write-Info "Update cancelled."
            exit 0
        }

        # Switch branch if needed
        if ($currentBranch -ne $targetBranch) {
            Write-Info "Switching to branch: $targetBranch"
            git checkout $targetBranch
        }

        Write-Info "Pulling latest changes..."
        git pull origin $targetBranch
        if ($LASTEXITCODE -ne 0) { Write-Err "git pull failed."; exit 1 }

        Write-Success "Code updated!"
        Write-Host ""
    }
    finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Manual (non-git) update
# ---------------------------------------------------------------------------
function Update-ViaCopy($DagdiDir) {
    Write-Header "Update from Downloaded Code"

    Write-Host "Please provide the path to the new Dagdi CLI source code"
    Write-Host "(the extracted folder containing pyproject.toml)."
    Write-Host ""
    $newSource = Read-Host "Path to new dagdi source"
    $newSource = $newSource.Trim('"').Trim("'")

    if (-not (Test-Path $newSource -PathType Container)) {
        Write-Err "Directory not found: $newSource"
        exit 1
    }

    if (-not (Test-Path (Join-Path $newSource "pyproject.toml"))) {
        Write-Err "Not a valid Dagdi source (no pyproject.toml in $newSource)"
        exit 1
    }

    # Show new version
    $initFile = Join-Path $newSource "src\dagdi\__init__.py"
    if (Test-Path $initFile) {
        $match = Select-String -Path $initFile -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match) {
            Write-Info "New version: $($match.Matches.Groups[1].Value)"
        }
    }

    Write-Host ""
    Write-Host "The following source directories will be replaced:" -ForegroundColor Cyan
    Write-Host "  src\dagdi\    (application source)"
    Write-Host "  tests\        (test suite)"
    Write-Host "  pyproject.toml, setup.sh, setup.ps1, update.sh, update.ps1"
    Write-Host ""
    Write-Host "The following will be PRESERVED (not overwritten):" -ForegroundColor Cyan
    Write-Host "  config\dagdi-*.yaml   (your infrastructure configs)"
    Write-Host "  .dagdi\               (your saved contexts)"
    Write-Host ""
    $proceed = Read-Host "Proceed with update? (y/n)"
    if ($proceed -ne "y") {
        Write-Info "Update cancelled."
        exit 0
    }

    Write-Info "Updating source files..."

    # Save user data to temp location
    $tempSave = Join-Path $env:TEMP "dagdi-update-$(Get-Date -Format 'yyyyMMddHHmmss')"
    New-Item -ItemType Directory -Path $tempSave -Force | Out-Null

    foreach ($udir in $UserDataDirs) {
        $src = Join-Path $DagdiDir $udir
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $tempSave $udir) -Recurse -Force
        }
    }

    # Copy new source files selectively
    $itemsToCopy = @("src", "tests", "documentation", "pyproject.toml",
                     "setup.sh", "setup.ps1", "update.sh", "update.ps1",
                     "README.md", ".gitignore")

    foreach ($item in $itemsToCopy) {
        $srcPath = Join-Path $newSource $item
        $dstPath = Join-Path $DagdiDir $item
        if (Test-Path $srcPath) {
            if (Test-Path $dstPath) {
                Remove-Item -Path $dstPath -Recurse -Force
            }
            Copy-Item -Path $srcPath -Destination $dstPath -Recurse -Force
        }
    }

    # Restore user data
    foreach ($udir in $UserDataDirs) {
        $saved = Join-Path $tempSave $udir
        if (Test-Path $saved) {
            $target = Join-Path $DagdiDir $udir
            Copy-Item -Path $saved -Destination $target -Recurse -Force
        }
    }
    Remove-Item -Path $tempSave -Recurse -Force -ErrorAction SilentlyContinue

    # Merge config: keep user dagdi-*.yaml, copy sample/template files
    $newConfig = Join-Path $newSource "config"
    if (Test-Path $newConfig) {
        $destConfig = Join-Path $DagdiDir "config"
        if (-not (Test-Path $destConfig)) { New-Item -ItemType Directory -Path $destConfig -Force | Out-Null }

        Get-ChildItem -Path $newConfig -File | ForEach-Object {
            if ($_.Name -notmatch '^dagdi-.*\.(yaml|yml)$') {
                Copy-Item -Path $_.FullName -Destination (Join-Path $destConfig $_.Name) -Force
            }
        }
    }

    Write-Success "Source files updated!"
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Reinstall dependencies
# ---------------------------------------------------------------------------
function Install-Dependencies($DagdiDir) {
    Write-Header "Reinstalling Dependencies"

    Push-Location $DagdiDir

    try {
        # Detect active environment
        if ($env:VIRTUAL_ENV) {
            Write-Info "Active virtual environment: $env:VIRTUAL_ENV"
        }
        elseif ($env:CONDA_DEFAULT_ENV) {
            Write-Info "Active conda environment: $env:CONDA_DEFAULT_ENV"
        }
        else {
            Write-Warn "No virtual environment detected."
            Write-Host "It's recommended to activate your dagdi virtual environment first."
            $cont = Read-Host "Continue installing without a virtual environment? (y/n)"
            if ($cont -ne "y") {
                Write-Info "Please activate your environment and run this script again."
                exit 0
            }
        }

        Write-Info "Installing dagdi and dependencies..."
        pip install -e ".[dev]"
        if ($LASTEXITCODE -ne 0) { Write-Err "pip install failed."; exit 1 }

        Write-Success "Dependencies installed!"
        Write-Host ""
    }
    finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
function Test-Update($DagdiDir) {
    Write-Header "Verifying Update"

    if (Test-CommandExists dagdi) {
        Write-Success "dagdi command is accessible!"

        $initFile = Join-Path $DagdiDir "src\dagdi\__init__.py"
        if (Test-Path $initFile) {
            $match = Select-String -Path $initFile -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
            if ($match) {
                Write-Success "Version: $($match.Matches.Groups[1].Value)"
            }
        }

        Write-Host ""
        Write-Info "Running 'dagdi --help' to verify:"
        Write-Host ""
        dagdi --help
        Write-Host ""

        # Quick config validation
        $configDir = Join-Path $DagdiDir "config"
        $yamlFiles = Get-ChildItem -Path $configDir -Filter "dagdi-*.yaml" -ErrorAction SilentlyContinue
        if ($yamlFiles.Count -gt 0) {
            Write-Info "Found $($yamlFiles.Count) config file(s). Running validation..."
            dagdi config validate 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Config validation passed!"
            }
            else {
                Write-Warn "Config validation had issues (this may be expected if configs need updating for the new version)."
            }
        }

        Write-Host ""
        Write-Success "Update complete!"
    }
    else {
        Write-Err "dagdi command not found after update."
        Write-Host ""
        Write-Host "Try activating your virtual environment and running:"
        Write-Host "   pip install -e `".[dev]`"" -ForegroundColor Cyan
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
function Start-Update {
    $dagdiDir = Find-Installation
    Show-CurrentVersion $dagdiDir

    $isGit = Test-Path (Join-Path $dagdiDir ".git")

    if ($isGit) {
        Write-Host "This installation is a git repository."
        Write-Host ""
        Write-Host "1) Update via git pull (recommended)"
        Write-Host "2) Update from downloaded code"
        Write-Host "3) Reinstall dependencies only (no code update)"
        Write-Host "4) Exit"
        Write-Host ""
        $choice = Read-Host "Enter your choice (1-4)"
    }
    else {
        Write-Host "This installation is not a git repository."
        Write-Host ""
        Write-Host "1) Update from downloaded code"
        Write-Host "2) Reinstall dependencies only (no code update)"
        Write-Host "3) Exit"
        Write-Host ""
        $choice = Read-Host "Enter your choice (1-3)"
        # Remap for non-git
        switch ($choice) {
            "1" { $choice = "2" }
            "2" { $choice = "3" }
            "3" { $choice = "4" }
        }
    }

    switch ($choice) {
        "1" {
            New-Backup $dagdiDir
            Update-ViaGit $dagdiDir
            Install-Dependencies $dagdiDir
            Test-Update $dagdiDir
        }
        "2" {
            New-Backup $dagdiDir
            Update-ViaCopy $dagdiDir
            Install-Dependencies $dagdiDir
            Test-Update $dagdiDir
        }
        "3" {
            Install-Dependencies $dagdiDir
            Test-Update $dagdiDir
        }
        "4" {
            Write-Info "Update cancelled."
            exit 0
        }
        default {
            Write-Err "Invalid choice."
            exit 1
        }
    }
}

Start-Update
