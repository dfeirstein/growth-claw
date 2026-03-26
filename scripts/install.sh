#!/bin/bash
# AutoGrow Installer
# Usage: curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install.sh | bash
#
# What this does:
#   1. Checks for Python 3.13+ (installs via uv if missing)
#   2. Creates ~/.growthclaw/ workspace
#   3. Creates a hidden venv at ~/.growthclaw/.venv/
#   4. Installs growthclaw into that venv
#   5. Adds 'growthclaw' command to your PATH
#   6. Optionally installs Claude Code CLI for harness mode
#   7. Runs 'growthclaw init'

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
BOLD='\033[1m'
NC='\033[0m'

print_step() { echo -e "${BLUE}==>${NC} $1"; }
print_ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
print_warn() { echo -e "${YELLOW}  !${NC} $1"; }
print_err()  { echo -e "${RED}  ✗${NC} $1"; }

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       AutoGrow — The Growth Compiler     ║${NC}"
echo -e "${GREEN}║       Database in. Growth out.           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ─── Step 0: Choose runtime mode ───────────────────────────
echo -e "${BOLD}How do you want to run AutoGrow?${NC}"
echo ""
echo -e "  ${GREEN}1${NC}) ${BOLD}Harness mode${NC} (recommended)"
echo "     Claude Code is the brain — composes messages using your brand voice,"
echo "     runs experiments, learns from outcomes, rewrites its own prompts."
echo "     Requires Claude Code CLI + Max plan."
echo ""
echo -e "  ${YELLOW}2${NC}) ${BOLD}Standalone mode${NC}"
echo "     Python engine handles everything via direct API calls."
echo "     Simpler setup. Requires an Anthropic or NVIDIA API key."
echo ""

# Read user choice (default to harness)
if [ -t 0 ]; then
    # Interactive terminal
    read -p "  Select [1/2] (default: 1): " MODE_CHOICE
else
    # Piped input (curl | bash) — default to harness
    MODE_CHOICE="1"
    echo "  Non-interactive install — defaulting to harness mode."
    echo "  Run this script directly (bash install.sh) for interactive mode."
    echo ""
fi

MODE_CHOICE="${MODE_CHOICE:-1}"
if [ "$MODE_CHOICE" = "2" ]; then
    INSTALL_MODE="standalone"
    echo ""
    print_ok "Standalone mode selected"
else
    INSTALL_MODE="harness"
    echo ""
    print_ok "Harness mode selected (recommended)"
fi

echo ""

# ─── Step 1: Check/install Python ─────────────────────────

print_step "Checking Python..."

find_python() {
    for cmd in python3.13 python3.14 python3; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
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

# ─── Step 2: Install Claude Code CLI (harness mode) ──────

if [ "$INSTALL_MODE" = "harness" ]; then
    print_step "Checking Claude Code CLI..."

    if command -v claude &>/dev/null; then
        print_ok "Claude Code: already installed"
    else
        # Check for Node.js
        if ! command -v node &>/dev/null; then
            print_warn "Node.js not found — needed for Claude Code CLI."

            if command -v brew &>/dev/null; then
                print_step "Installing Node.js via Homebrew..."
                brew install node
            else
                print_err "Cannot auto-install Node.js."
                echo ""
                echo "  Install Node.js first:"
                echo "    macOS:  brew install node"
                echo "    Linux:  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
                echo ""
                exit 1
            fi
        fi

        print_step "Installing Claude Code CLI..."
        npm install -g @anthropic-ai/claude-code
        print_ok "Claude Code: installed"
    fi

    # Check if Claude Code is authenticated
    if claude --version &>/dev/null 2>&1; then
        print_ok "Claude Code: $(claude --version 2>&1 || echo 'installed')"
    fi

    echo ""
    echo -e "  ${YELLOW}Important:${NC} Claude Code needs to be logged in before starting the harness."
    echo "  If you haven't logged in yet, run this after install:"
    echo ""
    echo -e "    ${GREEN}claude${NC}"
    echo ""
    echo "  This opens a browser to authenticate. You'll need a Max plan."
    echo "  Once logged in, type /exit to close the session."
    echo ""
fi

# ─── Step 3: Create workspace ────────────────────────────

print_step "Creating workspace at $GROWTHCLAW_HOME..."

mkdir -p "$GROWTHCLAW_HOME"
mkdir -p "$GROWTHCLAW_HOME/data/memory"
mkdir -p "$GROWTHCLAW_HOME/data/logs"

print_ok "Workspace: $GROWTHCLAW_HOME"

# ─── Step 4: Create venv ─────────────────────────────────

print_step "Creating virtual environment..."

if [ -d "$VENV_DIR" ]; then
    print_ok "Venv already exists"
else
    $PYTHON_CMD -m venv "$VENV_DIR"
    print_ok "Venv: $VENV_DIR"
fi

# ─── Step 5: Install growthclaw ──────────────────────────

print_step "Installing AutoGrow..."

"$VENV_DIR/bin/pip" install --upgrade pip -q 2>/dev/null
"$VENV_DIR/bin/pip" install growthclaw -q 2>/dev/null || {
    # If not on PyPI yet, install from GitHub
    print_warn "Not on PyPI yet — installing from GitHub..."
    "$VENV_DIR/bin/pip" install "git+https://github.com/dfeirstein/growth-claw.git" -q
}

print_ok "AutoGrow installed"

# ─── Step 6: Add to PATH ─────────────────────────────────

print_step "Adding 'growthclaw' to PATH..."

mkdir -p "$BIN_DIR"

# Create wrapper scripts
for cmd in growthclaw autogrow; do
    cat > "$BIN_DIR/$cmd" << WRAPPER
#!/bin/bash
exec "$HOME/.growthclaw/.venv/bin/growthclaw" "\$@"
WRAPPER
    chmod +x "$BIN_DIR/$cmd"
done

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

print_ok "Commands: growthclaw, autogrow"

# ─── Step 7: Write default config ────────────────────────

if [ "$INSTALL_MODE" = "standalone" ]; then
    DEFAULT_STANDALONE="true"
    DEFAULT_EVENT_MODE="poll"
else
    DEFAULT_STANDALONE="false"
    DEFAULT_EVENT_MODE="poll"
fi

# Only write .env if it doesn't exist (don't overwrite existing config)
if [ ! -f "$GROWTHCLAW_HOME/.env" ]; then
    cat > "$GROWTHCLAW_HOME/.env" << ENVFILE
# ═══════════════════════════════════════════════════════════════
# AutoGrow Configuration
# ═══════════════════════════════════════════════════════════════

# ─── Customer Database (READ-ONLY access to your business DB) ──
CUSTOMER_DATABASE_URL=postgresql://user:password@host:5432/dbname

# ─── Internal Database (AutoGrow's state — local PostgreSQL) ───
GROWTHCLAW_DATABASE_URL=postgresql://localhost:5432/autogrow_internal

# ─── Runtime Mode ──────────────────────────────────────────────
STANDALONE_MODE=$DEFAULT_STANDALONE
EVENT_MODE=$DEFAULT_EVENT_MODE
POLL_INTERVAL_SECONDS=30

# ─── LLM (only needed for standalone mode) ─────────────────────
ANTHROPIC_API_KEY=
# NVIDIA_API_KEY=

# ─── SMS — optional for dry run ────────────────────────────────
# TWILIO_ACCOUNT_SID=
# TWILIO_AUTH_TOKEN=
# TWILIO_FROM_NUMBER=

# ─── Email — optional for dry run ──────────────────────────────
GROWTHCLAW_EMAIL_PROVIDER=resend
# RESEND_API_KEY=
# GROWTHCLAW_FROM_EMAIL=
# GROWTHCLAW_FROM_NAME=

# ─── Business Context ──────────────────────────────────────────
GROWTHCLAW_BUSINESS_NAME=
GROWTHCLAW_BUSINESS_DESCRIPTION=

# ─── Safety (leave as-is for first run) ────────────────────────
GROWTHCLAW_DRY_RUN=true
GROWTHCLAW_CTA_URL=https://app.example.com
ENVFILE
    print_ok "Default config written to ~/.growthclaw/.env"
else
    print_ok "Config already exists at ~/.growthclaw/.env"
fi

# ─── Done ─────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Installation Complete!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

if [ "$INSTALL_MODE" = "harness" ]; then
    echo "  Mode: Harness (Claude Code is the brain)"
    echo ""
    echo "  Next steps:"
    echo ""
    echo -e "  ${BOLD}1.${NC} Open a new terminal (or run: source ~/.zshrc)"
    echo ""
    echo -e "  ${BOLD}2.${NC} Log in to Claude Code (if not already):"
    echo -e "     ${GREEN}claude${NC}"
    echo "     Authenticate in browser, then type /exit"
    echo ""
    echo -e "  ${BOLD}3.${NC} Create an internal database:"
    echo -e "     ${GREEN}createdb autogrow_internal${NC}"
    echo ""
    echo -e "  ${BOLD}4.${NC} Edit your credentials:"
    echo -e "     ${GREEN}nano ~/.growthclaw/.env${NC}"
    echo ""
    echo -e "  ${BOLD}5.${NC} Set up and discover your business:"
    echo -e "     ${GREEN}growthclaw init${NC}"
    echo -e "     ${GREEN}growthclaw migrate${NC}"
    echo -e "     ${GREEN}growthclaw onboard${NC}"
    echo ""
    echo -e "  ${BOLD}6.${NC} Approve triggers and start the compiler:"
    echo -e "     ${GREEN}growthclaw triggers approve --all${NC}"
    echo -e "     ${GREEN}growthclaw daemon start --harness${NC}"
    echo ""
else
    echo "  Mode: Standalone (direct API calls)"
    echo ""
    echo "  Next steps:"
    echo ""
    echo -e "  ${BOLD}1.${NC} Open a new terminal (or run: source ~/.zshrc)"
    echo ""
    echo -e "  ${BOLD}2.${NC} Create an internal database:"
    echo -e "     ${GREEN}createdb autogrow_internal${NC}"
    echo ""
    echo -e "  ${BOLD}3.${NC} Edit your credentials:"
    echo -e "     ${GREEN}nano ~/.growthclaw/.env${NC}"
    echo "     (set CUSTOMER_DATABASE_URL and ANTHROPIC_API_KEY at minimum)"
    echo ""
    echo -e "  ${BOLD}4.${NC} Set up and discover your business:"
    echo -e "     ${GREEN}growthclaw init${NC}"
    echo -e "     ${GREEN}growthclaw migrate${NC}"
    echo -e "     ${GREEN}growthclaw onboard${NC}"
    echo ""
    echo -e "  ${BOLD}5.${NC} Approve triggers and start:"
    echo -e "     ${GREEN}growthclaw triggers approve --all${NC}"
    echo -e "     ${GREEN}growthclaw start${NC}"
    echo ""
fi

# Remind to reload shell if PATH was updated
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "  ${YELLOW}First restart your terminal or run: source ~/.zshrc${NC}"
    echo ""
fi
