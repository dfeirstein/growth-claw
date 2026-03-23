#!/bin/bash
# GrowthClaw Installer
# Usage: curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install.sh | bash
#
# What this does:
#   1. Checks for Python 3.13+ (installs via uv if missing)
#   2. Creates ~/.growthclaw/ workspace
#   3. Creates a hidden venv at ~/.growthclaw/.venv/
#   4. Installs growthclaw into that venv
#   5. Adds 'growthclaw' command to your PATH
#   6. Runs 'growthclaw init'

set -e

GROWTHCLAW_HOME="$HOME/.growthclaw"
VENV_DIR="$GROWTHCLAW_HOME/.venv"
BIN_DIR="$HOME/.local/bin"
MIN_PYTHON="3.13"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() { echo -e "${BLUE}==>${NC} $1"; }
print_ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
print_warn() { echo -e "${YELLOW}  !${NC} $1"; }
print_err()  { echo -e "${RED}  ✗${NC} $1"; }

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       GrowthClaw Installer               ║${NC}"
echo -e "${GREEN}║       AI Marketing Engine                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ─── Step 1: Check/install Python ─────────────────────────────

print_step "Checking Python..."

find_python() {
    for cmd in python3.13 python3.14 python3; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 13 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_CMD=$(find_python) || true

if [ -z "$PYTHON_CMD" ]; then
    print_warn "Python 3.13+ not found."
    echo ""

    # Try to install via uv (fastest)
    if command -v uv &>/dev/null; then
        print_step "Installing Python 3.13 via uv..."
        uv python install 3.13
        PYTHON_CMD="uv run --python 3.13 python"
    elif command -v brew &>/dev/null; then
        print_step "Installing Python 3.13 via Homebrew..."
        brew install python@3.13
        PYTHON_CMD="python3.13"
    else
        print_err "Cannot auto-install Python 3.13+."
        echo ""
        echo "  Install one of these first:"
        echo "    macOS:  brew install python@3.13"
        echo "    Linux:  sudo apt install python3.13 python3.13-venv"
        echo "    Any:    curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.13"
        echo ""
        exit 1
    fi
fi

print_ok "Python: $($PYTHON_CMD --version 2>&1)"

# ─── Step 2: Create workspace ────────────────────────────────

print_step "Creating workspace at $GROWTHCLAW_HOME..."

mkdir -p "$GROWTHCLAW_HOME"
mkdir -p "$GROWTHCLAW_HOME/data/memory"
mkdir -p "$GROWTHCLAW_HOME/data/logs"

print_ok "Workspace: $GROWTHCLAW_HOME"

# ─── Step 3: Create venv ─────────────────────────────────────

print_step "Creating virtual environment..."

if [ -d "$VENV_DIR" ]; then
    print_ok "Venv already exists"
else
    $PYTHON_CMD -m venv "$VENV_DIR"
    print_ok "Venv: $VENV_DIR"
fi

# ─── Step 4: Install growthclaw ──────────────────────────────

print_step "Installing GrowthClaw..."

"$VENV_DIR/bin/pip" install --upgrade pip -q 2>/dev/null
"$VENV_DIR/bin/pip" install growthclaw -q 2>/dev/null || {
    # If not on PyPI yet, install from GitHub
    print_warn "Not on PyPI yet — installing from GitHub..."
    "$VENV_DIR/bin/pip" install "git+https://github.com/dfeirstein/growth-claw.git" -q
}

print_ok "GrowthClaw installed: $("$VENV_DIR/bin/growthclaw" --version 2>/dev/null || echo 'v0.2.0')"

# ─── Step 5: Add to PATH ─────────────────────────────────────

print_step "Adding 'growthclaw' to PATH..."

mkdir -p "$BIN_DIR"

# Create wrapper script (not symlink — handles venv activation)
cat > "$BIN_DIR/growthclaw" << 'WRAPPER'
#!/bin/bash
exec "$HOME/.growthclaw/.venv/bin/growthclaw" "$@"
WRAPPER
chmod +x "$BIN_DIR/growthclaw"

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    SHELL_RC=""
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_RC="$HOME/.bash_profile"
    fi

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
            print_ok "Added ~/.local/bin to PATH in $SHELL_RC"
        fi
    fi
    export PATH="$BIN_DIR:$PATH"
fi

print_ok "Command: growthclaw"

# ─── Step 6: Run init ────────────────────────────────────────

print_step "Initializing GrowthClaw..."
echo ""

"$BIN_DIR/growthclaw" init

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Installation Complete!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  Workspace: ~/.growthclaw/"
echo "  Command:   growthclaw"
echo ""
echo "  Quick start:"
echo "    growthclaw setup     # Configure DB, keys, channels"
echo "    growthclaw migrate   # Create internal tables"
echo "    growthclaw onboard   # Discover your database"
echo ""

# Remind to reload shell if PATH was updated
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "  ${YELLOW}Restart your terminal or run: source ~/.zshrc${NC}"
    echo ""
fi
