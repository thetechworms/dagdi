################################################################################
#                    Dagdi CLI - Interactive Setup Script (Windows)
#
# This script helps you install and set up Dagdi CLI on Windows.
# It supports conda, uv, and plain Python (venv) installations.
#
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1
################################################################################

$ErrorActionPreference = "Stop"

function Write-Header($Message) {
    Write-Host ""
    Write-Host "================================" -ForegroundColor Blue
    Write-Host $Message -ForegroundColor Blue
    Write-Host "================================" -ForegroundColor Blue
    Write-Host ""
}

function Write-Success($Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Err($Message) {
    Write-Host "[X]  $Message" -ForegroundColor Red
}

function Write-Warn($Message) {
    Write-Host "[!]  $Message" -ForegroundColor Yellow
}

function Write-Info($Message) {
    Write-Host "[i]  $Message" -ForegroundColor Cyan
}

function Test-CommandExists($Name) {
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-ProjectRoot {
    if (-not (Test-Path "pyproject.toml")) {
        Write-Err "pyproject.toml not found!"
        Write-Host ""
        Write-Host "Please run this script from the Dagdi CLI project root directory."
        exit 1
    }
}

function Install-Dagdi($PipCmd) {
    Write-Header "Installing Dagdi CLI"
    Assert-ProjectRoot

    Write-Info "Installing Dagdi CLI and dependencies..."
    & $PipCmd install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { Write-Err "pip install failed."; exit 1 }

    Write-Success "Dagdi CLI installed successfully!"
    Write-Host ""
}

function Show-NextSteps($EnvName, $EnvType) {
    Write-Header "Verifying Installation"

    if (Test-CommandExists dagdi) {
        Write-Success "Dagdi CLI is installed and accessible!"
        Write-Host ""

        Write-Info "Running 'dagdi --help':"
        Write-Host ""
        dagdi --help
        Write-Host ""

        Write-Header "Next Steps"

        Write-Host "1. Generate configuration template:"
        Write-Host "   dagdi config generate" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "2. Edit the configuration file:"
        Write-Host "   notepad config\dagdi-template.yaml" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "3. Validate configuration:"
        Write-Host "   dagdi config validate" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "4. Set context:"
        Write-Host "   dagdi context set -p <product> -e <environment>" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "5. Start using Dagdi:"
        Write-Host "   dagdi list products" -ForegroundColor Cyan
        Write-Host ""

        switch ($EnvType) {
            "conda" {
                Write-Host "To activate the environment in the future, run:"
                Write-Host "   conda activate $EnvName" -ForegroundColor Cyan
                Write-Host ""
            }
            "uv" {
                Write-Host "To activate the environment in the future, run:"
                Write-Host "   .venv\Scripts\activate" -ForegroundColor Cyan
                Write-Host ""
            }
            "python" {
                Write-Host "To activate the environment in the future, run:"
                Write-Host "   $EnvName\Scripts\Activate.ps1" -ForegroundColor Cyan
                Write-Host ""
            }
        }

        Write-Host "For more information, see the documentation/ directory."
        Write-Host ""
        Write-Success "Setup complete! Happy infrastructure management!"
        Write-Host ""
    }
    else {
        Write-Err "Dagdi CLI is not accessible!"
        Write-Host ""
        Write-Host "This might be because:"
        Write-Host "1. The installation failed"
        Write-Host "2. The virtual environment is not activated"
        Write-Host "3. The PATH is not updated"
        Write-Host ""

        switch ($EnvType) {
            "conda" {
                Write-Host "Try activating the environment:"
                Write-Host "   conda activate $EnvName" -ForegroundColor Cyan
            }
            "uv" {
                Write-Host "Try activating the environment:"
                Write-Host "   .venv\Scripts\activate" -ForegroundColor Cyan
            }
            "python" {
                Write-Host "Try activating the environment:"
                Write-Host "   $EnvName\Scripts\Activate.ps1" -ForegroundColor Cyan
            }
        }
        Write-Host ""
        Write-Host "Then try running:"
        Write-Host "   dagdi --help" -ForegroundColor Cyan
        Write-Host ""
        exit 1
    }
}

# ---------- Conda ----------

function Setup-Conda {
    Write-Header "Conda Setup"

    if (-not (Test-CommandExists conda)) {
        Write-Err "Conda is not installed or not in PATH."
        Write-Host ""
        Write-Host "Install from: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html"
        Write-Host ""
        $resp = Read-Host "Press Enter after installing Conda, or type 'skip' to choose another method"
        if ($resp -eq "skip") { Show-Menu; return }
        if (-not (Test-CommandExists conda)) {
            Write-Err "Conda still not found. Please install it first."
            exit 1
        }
    }

    Write-Success "Conda found: $(conda --version)"
    Write-Host ""

    $envName = Read-Host "Enter environment name (default: dagdi)"
    if ([string]::IsNullOrWhiteSpace($envName)) { $envName = "dagdi" }

    $existing = conda env list 2>&1 | Select-String "^$envName\s"
    if ($existing) {
        Write-Warn "Environment '$envName' already exists."
        $use = Read-Host "Do you want to use the existing environment? (y/n)"
        if ($use -ne "y") {
            $envName = Read-Host "Enter a different environment name"
        }
    }

    if (-not $existing -or $use -eq "n") {
        Write-Info "Creating conda environment: $envName"
        conda create -n $envName python=3.10 -y
        if ($LASTEXITCODE -ne 0) { Write-Err "conda create failed."; exit 1 }
        Write-Success "Environment created!"
    }

    Write-Info "Activating environment..."
    conda activate $envName
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Could not activate via 'conda activate'. Trying conda shell hook..."
        $hookScript = (conda shell.powershell activate $envName) -join "`n"
        Invoke-Expression $hookScript
    }
    Write-Success "Environment activated!"
    Write-Host ""

    Install-Dagdi "pip"
    Show-NextSteps $envName "conda"
}

# ---------- uv ----------

function Setup-Uv {
    Write-Header "uv Setup"

    if (-not (Test-CommandExists uv)) {
        Write-Err "uv is not installed or not in PATH."
        Write-Host ""
        Write-Host "Install uv with:"
        Write-Host "   powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Or via pip:"
        Write-Host "   pip install uv" -ForegroundColor Cyan
        Write-Host ""
        $resp = Read-Host "Press Enter after installing uv, or type 'skip' to choose another method"
        if ($resp -eq "skip") { Show-Menu; return }
        if (-not (Test-CommandExists uv)) {
            Write-Err "uv still not found. Please install it first."
            exit 1
        }
    }

    Write-Success "uv found: $(uv --version)"
    Write-Host ""

    Write-Info "Creating virtual environment with uv (Python 3.10)..."
    uv venv .venv --python 3.10
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Python 3.10 not available, falling back to default Python..."
        uv venv .venv
        if ($LASTEXITCODE -ne 0) { Write-Err "uv venv creation failed."; exit 1 }
    }
    Write-Success "Virtual environment created at .venv\"
    Write-Host ""

    Write-Info "Activating virtual environment..."
    & .venv\Scripts\Activate.ps1
    Write-Success "Virtual environment activated!"
    Write-Host ""

    Write-Info "Installing Dagdi CLI and dependencies with uv..."
    uv pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { Write-Err "uv pip install failed."; exit 1 }

    Write-Success "Dagdi CLI installed successfully!"
    Write-Host ""

    Show-NextSteps ".venv" "uv"
}

# ---------- Plain Python ----------

function Setup-Python {
    Write-Header "Plain Python Setup"

    $pythonCmd = $null
    if (Test-CommandExists python) { $pythonCmd = "python" }
    elseif (Test-CommandExists python3) { $pythonCmd = "python3" }
    else {
        Write-Err "Python is not installed or not in PATH."
        Write-Host ""
        Write-Host "Install from: https://www.python.org/downloads/"
        exit 1
    }

    $versionOutput = & $pythonCmd --version 2>&1
    $versionString = ($versionOutput -replace "Python\s+", "").Trim()
    $parts = $versionString.Split(".")
    $major = [int]$parts[0]
    $minor = [int]$parts[1]

    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 9)) {
        Write-Err "Python 3.9+ is required. You have Python $versionString"
        exit 1
    }

    Write-Success "Python found: $versionString (command: $pythonCmd)"
    Write-Host ""

    Write-Host "It's recommended to use a virtual environment."
    $createVenv = Read-Host "Do you want to create a virtual environment? (y/n)"

    $envName = "dagdi"
    if ($createVenv -eq "y") {
        $envName = Read-Host "Enter virtual environment name (default: dagdi)"
        if ([string]::IsNullOrWhiteSpace($envName)) { $envName = "dagdi" }

        Write-Info "Creating virtual environment: $envName"
        & $pythonCmd -m venv $envName
        if ($LASTEXITCODE -ne 0) { Write-Err "venv creation failed."; exit 1 }

        Write-Success "Virtual environment created!"
        Write-Host ""

        Write-Info "Activating virtual environment..."
        & "$envName\Scripts\Activate.ps1"
        Write-Success "Virtual environment activated!"
        Write-Host ""

        Install-Dagdi "pip"
    }
    else {
        Write-Warn "Installing globally. This may require administrator privileges."
        Install-Dagdi "pip"
    }

    Show-NextSteps $envName "python"
}

# ---------- Menu ----------

function Show-Menu {
    Write-Header "Dagdi CLI - Setup Script (Windows)"

    Write-Host "Welcome to Dagdi CLI setup!"
    Write-Host ""
    Write-Host "This script will help you install Dagdi CLI on your machine."
    Write-Host ""
    Write-Host "Please select your Python environment manager:"
    Write-Host ""
    Write-Host "1) uv        (recommended - fast, modern)"
    Write-Host "2) Conda"
    Write-Host "3) Plain Python (system or venv)"
    Write-Host "4) Exit"
    Write-Host ""

    $choice = Read-Host "Enter your choice (1-4)"

    switch ($choice) {
        "1" { Setup-Uv }
        "2" { Setup-Conda }
        "3" { Setup-Python }
        "4" { Write-Info "Setup cancelled."; exit 0 }
        default {
            Write-Err "Invalid choice. Please try again."
            Show-Menu
        }
    }
}

Show-Menu
