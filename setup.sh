#!/bin/bash

################################################################################
#                    Dagdi CLI - Interactive Setup Script
#
# This script helps you install and set up Dagdi CLI on your machine.
# It supports conda, pyenv, and plain Python installations.
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Main setup
main() {
    print_header "Dagdi CLI - Setup Script"
    
    echo "Welcome to Dagdi CLI setup!"
    echo ""
    echo "This script will help you install Dagdi CLI on your machine."
    echo ""
    echo "Please select your Python environment manager:"
    echo ""
    echo "1) Conda (recommended)"
    echo "2) Pyenv"
    echo "3) Plain Python (system or venv)"
    echo "4) Exit"
    echo ""
    
    read -p "Enter your choice (1-4): " choice
    
    case $choice in
        1)
            setup_conda
            ;;
        2)
            setup_pyenv
            ;;
        3)
            setup_plain_python
            ;;
        4)
            print_info "Setup cancelled."
            exit 0
            ;;
        *)
            print_error "Invalid choice. Please try again."
            main
            ;;
    esac
}

# Conda setup
setup_conda() {
    print_header "Conda Setup"
    
    # Check if conda is installed
    if ! command_exists conda; then
        print_error "Conda is not installed or not in PATH."
        echo ""
        echo "Please install Conda from: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html"
        echo ""
        read -p "Press Enter after installing Conda, or type 'skip' to use another method: " response
        
        if [ "$response" = "skip" ]; then
            main
            return
        fi
        
        if ! command_exists conda; then
            print_error "Conda still not found. Please install it first."
            exit 1
        fi
    fi
    
    print_success "Conda found: $(conda --version)"
    echo ""
    
    # Ask for environment name
    read -p "Enter environment name (default: dagdi): " env_name
    env_name=${env_name:-dagdi}
    
    # Check if environment already exists
    if conda env list | grep -q "^$env_name "; then
        print_warning "Environment '$env_name' already exists."
        read -p "Do you want to use the existing environment? (y/n): " use_existing
        
        if [ "$use_existing" != "y" ]; then
            read -p "Enter a different environment name: " env_name
        fi
    fi
    
    print_info "Creating conda environment: $env_name"
    conda create -n "$env_name" python=3.10 -y
    
    print_success "Environment created!"
    echo ""
    print_info "Activating environment..."
    
    # Source conda.sh to enable conda activate
    if [ -f "$CONDA_PREFIX/etc/profile.d/conda.sh" ]; then
        source "$CONDA_PREFIX/etc/profile.d/conda.sh"
    elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
    elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
    fi
    
    conda activate "$env_name"
    
    print_success "Environment activated!"
    echo ""
    
    # Install Dagdi
    install_dagdi
    
    # Verify installation
    verify_installation "$env_name" "conda"
}

# Pyenv setup
setup_pyenv() {
    print_header "Pyenv Setup"
    
    # Check if pyenv is installed
    if ! command_exists pyenv; then
        print_error "Pyenv is not installed or not in PATH."
        echo ""
        echo "Please install Pyenv from: https://github.com/pyenv/pyenv#installation"
        echo ""
        read -p "Press Enter after installing Pyenv, or type 'skip' to use another method: " response
        
        if [ "$response" = "skip" ]; then
            main
            return
        fi
        
        if ! command_exists pyenv; then
            print_error "Pyenv still not found. Please install it first."
            exit 1
        fi
    fi
    
    print_success "Pyenv found: $(pyenv --version)"
    echo ""
    
    # Ask for Python version
    read -p "Enter Python version (default: 3.10.0): " python_version
    python_version=${python_version:-3.10.0}
    
    print_info "Installing Python $python_version with pyenv..."
    pyenv install -s "$python_version"
    
    print_success "Python $python_version installed!"
    echo ""
    
    # Create virtual environment
    read -p "Enter virtual environment name (default: dagdi): " venv_name
    venv_name=${venv_name:-dagdi}
    
    print_info "Creating virtual environment: $venv_name"
    python -m venv "$venv_name"
    
    print_success "Virtual environment created!"
    echo ""
    print_info "Activating virtual environment..."
    
    source "$venv_name/bin/activate"
    
    print_success "Virtual environment activated!"
    echo ""
    
    # Install Dagdi
    install_dagdi
    
    # Verify installation
    verify_installation "$venv_name" "pyenv"
}

# Plain Python setup
setup_plain_python() {
    print_header "Plain Python Setup"
    
    # Check if python3 is installed
    if ! command_exists python3; then
        print_error "Python 3 is not installed or not in PATH."
        echo ""
        echo "Please install Python 3 from: https://www.python.org/downloads/"
        echo ""
        exit 1
    fi
    
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    print_success "Python found: $python_version"
    echo ""
    
    # Check Python version
    major_version=$(echo "$python_version" | cut -d. -f1)
    minor_version=$(echo "$python_version" | cut -d. -f2)
    
    if [ "$major_version" -lt 3 ] || ([ "$major_version" -eq 3 ] && [ "$minor_version" -lt 9 ]); then
        print_error "Python 3.9+ is required. You have Python $python_version"
        exit 1
    fi
    
    # Ask if user wants to create virtual environment
    echo "It's recommended to use a virtual environment."
    read -p "Do you want to create a virtual environment? (y/n): " create_venv
    
    if [ "$create_venv" = "y" ]; then
        read -p "Enter virtual environment name (default: dagdi): " venv_name
        venv_name=${venv_name:-dagdi}
        
        print_info "Creating virtual environment: $venv_name"
        python3 -m venv "$venv_name"
        
        print_success "Virtual environment created!"
        echo ""
        print_info "Activating virtual environment..."
        
        source "$venv_name/bin/activate"
        
        print_success "Virtual environment activated!"
        echo ""
    else
        print_warning "Installing globally. This may require sudo."
    fi
    
    # Install Dagdi
    install_dagdi
    
    # Verify installation
    verify_installation "dagdi" "python"
}

# Install Dagdi
install_dagdi() {
    print_header "Installing Dagdi CLI"
    
    # Check if we're in the right directory
    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml not found!"
        echo ""
        echo "Please run this script from the Dagdi CLI project root directory."
        echo ""
        exit 1
    fi
    
    print_info "Installing Dagdi CLI and dependencies..."
    pip install -e ".[dev]"
    
    print_success "Dagdi CLI installed successfully!"
    echo ""
}

# Verify installation
verify_installation() {
    print_header "Verifying Installation"
    
    local env_name=$1
    local env_type=$2
    
    # Check if dagdi command works
    if command_exists dagdi; then
        print_success "Dagdi CLI is installed and accessible!"
        echo ""
        
        # Show version/help
        print_info "Running 'dagdi --help':"
        echo ""
        dagdi --help | head -20
        echo ""
        
        # Next steps
        print_header "Next Steps"
        
        echo "1. Generate configuration template:"
        echo "   ${BLUE}dagdi config generate${NC}"
        echo ""
        
        echo "2. Edit the configuration file:"
        echo "   ${BLUE}nano config/dagdi-template.yaml${NC}"
        echo ""
        
        echo "3. Validate configuration:"
        echo "   ${BLUE}dagdi config validate${NC}"
        echo ""
        
        echo "4. Set context:"
        echo "   ${BLUE}dagdi context set -p <product> -e <environment>${NC}"
        echo ""
        
        echo "5. Start using Dagdi:"
        echo "   ${BLUE}dagdi list products${NC}"
        echo ""
        
        # Activation instructions
        if [ "$env_type" = "conda" ]; then
            echo "To activate the environment in the future, run:"
            echo "   ${BLUE}conda activate $env_name${NC}"
            echo ""
        elif [ "$env_type" = "pyenv" ]; then
            echo "To activate the environment in the future, run:"
            echo "   ${BLUE}source $env_name/bin/activate${NC}"
            echo ""
        elif [ "$env_type" = "python" ]; then
            echo "To activate the environment in the future, run:"
            echo "   ${BLUE}source $env_name/bin/activate${NC}"
            echo ""
        fi
        
        echo "For more information, see:"
        echo "   - User Guide: ${BLUE}USER_GUIDE.md${NC}"
        echo "   - Examples: ${BLUE}EXAMPLE_CONFIGURATIONS.md${NC}"
        echo "   - README: ${BLUE}README_FINAL.md${NC}"
        echo ""
        
        print_success "Setup complete! Happy infrastructure management! 🚀"
        echo ""
    else
        print_error "Dagdi CLI is not accessible!"
        echo ""
        echo "This might be because:"
        echo "1. The installation failed"
        echo "2. The virtual environment is not activated"
        echo "3. The PATH is not updated"
        echo ""
        
        if [ "$env_type" = "conda" ]; then
            echo "Try activating the environment:"
            echo "   ${BLUE}conda activate $env_name${NC}"
            echo ""
        elif [ "$env_type" = "pyenv" ] || [ "$env_type" = "python" ]; then
            echo "Try activating the environment:"
            echo "   ${BLUE}source $env_name/bin/activate${NC}"
            echo ""
        fi
        
        echo "Then try running:"
        echo "   ${BLUE}dagdi --help${NC}"
        echo ""
        
        exit 1
    fi
}

# Run main function
main
