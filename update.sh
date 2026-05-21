#!/bin/bash

################################################################################
#                    Dagdi CLI - Interactive Update Script
#
# This script helps you update an existing Dagdi CLI installation.
# It supports git-based updates and manual (downloaded) updates.
#
# Usage: bash update.sh
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

BACKUP_EXCLUDE_DIRS=(".git" "venv" ".venv" "__pycache__" "*.egg-info" ".eggs" "node_modules" ".tox" ".mypy_cache" ".pytest_cache" ".ruff_cache")
USER_DATA_DIRS=("config" ".dagdi")

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info()    { echo -e "${BLUE}ℹ $1${NC}"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Locate existing installation
# ---------------------------------------------------------------------------
locate_installation() {
    print_header "Dagdi CLI - Update Script"

    echo "This script will update your existing Dagdi CLI installation."
    echo ""

    # Check if current directory is a dagdi project
    if [ -f "pyproject.toml" ] && grep -q 'name.*=.*"dagdi-cli"' pyproject.toml 2>/dev/null; then
        print_info "Detected Dagdi CLI project in current directory: $(pwd)"
        read -p "Use this location? (y/n): " use_current
        if [ "$use_current" = "y" ]; then
            DAGDI_DIR="$(pwd)"
            return
        fi
    fi

    read -p "Enter the path to your existing Dagdi CLI installation: " install_path

    # Expand ~ if present
    install_path="${install_path/#\~/$HOME}"

    if [ ! -d "$install_path" ]; then
        print_error "Directory not found: $install_path"
        exit 1
    fi

    if [ ! -f "$install_path/pyproject.toml" ]; then
        print_error "Not a valid Dagdi project (no pyproject.toml found in $install_path)"
        exit 1
    fi

    if ! grep -q 'name.*=.*"dagdi-cli"' "$install_path/pyproject.toml" 2>/dev/null; then
        print_error "pyproject.toml exists but does not appear to be dagdi-cli."
        exit 1
    fi

    DAGDI_DIR="$install_path"
    print_success "Found Dagdi CLI at: $DAGDI_DIR"
}

# ---------------------------------------------------------------------------
# Show current version info
# ---------------------------------------------------------------------------
show_current_version() {
    echo ""
    if [ -f "$DAGDI_DIR/src/dagdi/__init__.py" ]; then
        current_version=$(grep '__version__' "$DAGDI_DIR/src/dagdi/__init__.py" 2>/dev/null | head -1 | sed 's/.*"\(.*\)".*/\1/')
        if [ -n "$current_version" ]; then
            print_info "Current installed version: $current_version"
        fi
    fi

    if [ -d "$DAGDI_DIR/.git" ]; then
        current_commit=$(git -C "$DAGDI_DIR" log --oneline -1 2>/dev/null || echo "unknown")
        current_branch=$(git -C "$DAGDI_DIR" branch --show-current 2>/dev/null || echo "unknown")
        print_info "Current branch: $current_branch"
        print_info "Current commit: $current_commit"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
create_backup() {
    print_header "Backup"

    read -p "Do you want to create a backup of the current installation? (y/n): " do_backup
    if [ "$do_backup" != "y" ]; then
        print_warning "Skipping backup."
        return
    fi

    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    BACKUP_DIR="${DAGDI_DIR}-backup-${TIMESTAMP}"

    print_info "Creating backup at: $BACKUP_DIR"

    # Build rsync exclude args
    EXCLUDE_ARGS=""
    for dir in "${BACKUP_EXCLUDE_DIRS[@]}"; do
        EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude=$dir"
    done

    if command_exists rsync; then
        rsync -a $EXCLUDE_ARGS "$DAGDI_DIR/" "$BACKUP_DIR/"
    else
        # Fallback: cp then remove excluded dirs
        cp -r "$DAGDI_DIR" "$BACKUP_DIR"
        for dir in "${BACKUP_EXCLUDE_DIRS[@]}"; do
            find "$BACKUP_DIR" -name "$dir" -type d -exec rm -rf {} + 2>/dev/null || true
        done
    fi

    print_success "Backup created at: $BACKUP_DIR"
    echo ""
}

# ---------------------------------------------------------------------------
# Git-based update
# ---------------------------------------------------------------------------
update_via_git() {
    print_header "Update via Git"

    cd "$DAGDI_DIR"

    # Check for uncommitted changes
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        print_warning "You have uncommitted changes:"
        git status --short
        echo ""
        read -p "Continue anyway? Changes may conflict with the update. (y/n): " cont
        if [ "$cont" != "y" ]; then
            print_info "Update cancelled. Please commit or stash your changes first."
            exit 0
        fi
    fi

    # Show current branch and ask which to pull
    current_branch=$(git branch --show-current 2>/dev/null || echo "main")
    echo "Current branch: $current_branch"
    read -p "Branch to update from (default: $current_branch): " target_branch
    target_branch=${target_branch:-$current_branch}

    # Fetch and show what will change
    print_info "Fetching latest changes..."
    git fetch origin "$target_branch"
    echo ""

    incoming=$(git log --oneline HEAD..origin/"$target_branch" 2>/dev/null)
    if [ -z "$incoming" ]; then
        print_success "Already up to date! No new commits."
        echo ""
        read -p "Reinstall dependencies anyway? (y/n): " reinstall_anyway
        if [ "$reinstall_anyway" != "y" ]; then
            print_info "Nothing to do."
            exit 0
        fi
        return
    fi

    echo -e "${CYAN}Incoming changes:${NC}"
    echo "$incoming"
    echo ""

    files_changed=$(git diff --stat HEAD..origin/"$target_branch" 2>/dev/null)
    echo -e "${CYAN}Files changed:${NC}"
    echo "$files_changed"
    echo ""

    read -p "Apply these changes? (y/n): " apply
    if [ "$apply" != "y" ]; then
        print_info "Update cancelled."
        exit 0
    fi

    # If not on the target branch, switch to it
    if [ "$current_branch" != "$target_branch" ]; then
        print_info "Switching to branch: $target_branch"
        git checkout "$target_branch"
    fi

    print_info "Pulling latest changes..."
    git pull origin "$target_branch"

    print_success "Code updated!"
    echo ""
}

# ---------------------------------------------------------------------------
# Manual (non-git) update
# ---------------------------------------------------------------------------
update_via_copy() {
    print_header "Update from Downloaded Code"

    echo "Please provide the path to the new Dagdi CLI source code"
    echo "(the extracted folder containing pyproject.toml)."
    echo ""
    read -p "Path to new dagdi source: " new_source

    # Expand ~
    new_source="${new_source/#\~/$HOME}"

    if [ ! -d "$new_source" ]; then
        print_error "Directory not found: $new_source"
        exit 1
    fi

    if [ ! -f "$new_source/pyproject.toml" ]; then
        print_error "Not a valid Dagdi source (no pyproject.toml in $new_source)"
        exit 1
    fi

    # Show new version
    if [ -f "$new_source/src/dagdi/__init__.py" ]; then
        new_version=$(grep '__version__' "$new_source/src/dagdi/__init__.py" 2>/dev/null | head -1 | sed 's/.*"\(.*\)".*/\1/')
        if [ -n "$new_version" ]; then
            print_info "New version: $new_version"
        fi
    fi

    # Determine which source files will be replaced
    echo ""
    echo -e "${CYAN}The following source directories will be replaced:${NC}"
    echo "  src/dagdi/    (application source)"
    echo "  tests/        (test suite)"
    echo "  pyproject.toml, setup.sh, setup.ps1, update.sh, update.ps1"
    echo ""
    echo -e "${CYAN}The following will be PRESERVED (not overwritten):${NC}"
    echo "  config/dagdi-*.yaml   (your infrastructure configs)"
    echo "  .dagdi/               (your saved contexts)"
    echo ""
    read -p "Proceed with update? (y/n): " proceed
    if [ "$proceed" != "y" ]; then
        print_info "Update cancelled."
        exit 0
    fi

    print_info "Updating source files..."

    # Save user data to temp location
    TEMP_SAVE=$(mktemp -d)
    for udir in "${USER_DATA_DIRS[@]}"; do
        if [ -d "$DAGDI_DIR/$udir" ]; then
            cp -r "$DAGDI_DIR/$udir" "$TEMP_SAVE/$udir"
        fi
    done

    # Copy new source, excluding user data dirs and git
    if command_exists rsync; then
        rsync -a \
            --exclude=".git" \
            --exclude="venv" \
            --exclude=".venv" \
            --exclude="__pycache__" \
            --exclude="*.egg-info" \
            --exclude=".eggs" \
            "$new_source/" "$DAGDI_DIR/"
    else
        # Fallback: copy new source files selectively
        for item in src tests documentation pyproject.toml setup.sh setup.ps1 update.sh update.ps1 README.md .gitignore; do
            if [ -e "$new_source/$item" ]; then
                rm -rf "$DAGDI_DIR/$item"
                cp -r "$new_source/$item" "$DAGDI_DIR/$item"
            fi
        done
    fi

    # Restore user data
    for udir in "${USER_DATA_DIRS[@]}"; do
        if [ -d "$TEMP_SAVE/$udir" ]; then
            cp -r "$TEMP_SAVE/$udir" "$DAGDI_DIR/$udir"
        fi
    done
    rm -rf "$TEMP_SAVE"

    # Merge config: keep user's dagdi-*.yaml, but copy sample/template files
    if [ -d "$new_source/config" ]; then
        for f in "$new_source/config/"*; do
            fname=$(basename "$f")
            case "$fname" in
                dagdi-*.yaml|dagdi-*.yml)
                    # Skip - these are user configs
                    ;;
                *)
                    cp "$f" "$DAGDI_DIR/config/$fname"
                    ;;
            esac
        done
    fi

    print_success "Source files updated!"
    echo ""
}

# ---------------------------------------------------------------------------
# Reinstall dependencies
# ---------------------------------------------------------------------------
reinstall_dependencies() {
    print_header "Reinstalling Dependencies"

    cd "$DAGDI_DIR"

    # Detect active virtual environment
    if [ -n "$VIRTUAL_ENV" ]; then
        print_info "Active virtual environment: $VIRTUAL_ENV"
    elif [ -n "$CONDA_DEFAULT_ENV" ]; then
        print_info "Active conda environment: $CONDA_DEFAULT_ENV"
    else
        print_warning "No virtual environment detected."
        echo "It's recommended to activate your dagdi virtual environment first."
        read -p "Continue installing without a virtual environment? (y/n): " cont
        if [ "$cont" != "y" ]; then
            print_info "Please activate your environment and run this script again."
            exit 0
        fi
    fi

    print_info "Installing dagdi and dependencies..."
    pip install -e ".[dev]"

    print_success "Dependencies installed!"
    echo ""
}

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
verify_update() {
    print_header "Verifying Update"

    if command_exists dagdi; then
        print_success "dagdi command is accessible!"

        if [ -f "$DAGDI_DIR/src/dagdi/__init__.py" ]; then
            new_version=$(grep '__version__' "$DAGDI_DIR/src/dagdi/__init__.py" 2>/dev/null | head -1 | sed 's/.*"\(.*\)".*/\1/')
            if [ -n "$new_version" ]; then
                print_success "Version: $new_version"
            fi
        fi

        echo ""
        print_info "Running 'dagdi --help' to verify:"
        echo ""
        dagdi --help | head -10
        echo ""

        # Quick test: validate config if configs exist
        yaml_count=$(find "$DAGDI_DIR/config" -name "dagdi-*.yaml" -o -name "dagdi-*.yml" 2>/dev/null | wc -l)
        if [ "$yaml_count" -gt 0 ]; then
            print_info "Found $yaml_count config file(s). Running validation..."
            dagdi config validate 2>/dev/null && print_success "Config validation passed!" || print_warning "Config validation had issues (this is expected if configs need updating for the new version)."
        fi

        echo ""
        print_success "Update complete!"
    else
        print_error "dagdi command not found after update."
        echo ""
        echo "Try activating your virtual environment and running:"
        echo "   pip install -e \".[dev]\""
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    locate_installation
    show_current_version

    # Choose update method
    if [ -d "$DAGDI_DIR/.git" ]; then
        echo "This installation is a git repository."
        echo ""
        echo "1) Update via git pull (recommended)"
        echo "2) Update from downloaded code"
        echo "3) Reinstall dependencies only (no code update)"
        echo "4) Exit"
        echo ""
        read -p "Enter your choice (1-4): " method
    else
        echo "This installation is not a git repository."
        echo ""
        echo "1) Update from downloaded code"
        echo "2) Reinstall dependencies only (no code update)"
        echo "3) Exit"
        echo ""
        read -p "Enter your choice (1-3): " method
        # Remap choices for non-git
        case $method in
            1) method=2 ;;
            2) method=3 ;;
            3) method=4 ;;
        esac
    fi

    case $method in
        1)
            create_backup
            update_via_git
            reinstall_dependencies
            verify_update
            ;;
        2)
            create_backup
            update_via_copy
            reinstall_dependencies
            verify_update
            ;;
        3)
            reinstall_dependencies
            verify_update
            ;;
        4)
            print_info "Update cancelled."
            exit 0
            ;;
        *)
            print_error "Invalid choice."
            exit 1
            ;;
    esac
}

main
