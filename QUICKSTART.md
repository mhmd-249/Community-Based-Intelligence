# CBI Project Quick Start Guide

## Prerequisites Checklist

Before you begin, ensure you have the following accounts and tools ready.

### Required Accounts

| Account | Purpose | How to Get |
|---------|---------|------------|
| **Anthropic Account** | Claude Code access + API keys | [console.anthropic.com](https://console.anthropic.com) |
| **Claude Pro/Max Subscription** | Required for Claude Code CLI | [claude.ai/upgrade](https://claude.ai) ($20-200/month) |
| **Telegram Account** | Create bot for MVP testing | [telegram.org](https://telegram.org) |
| **GitHub Account** | Version control | [github.com](https://github.com) |
| **AWS Account** | Production deployment (later) | [aws.amazon.com](https://aws.amazon.com) |

### Required Software

```bash
# Check if you have these installed
node --version      # Need v18+ 
python --version    # Need 3.11+
docker --version    # Need 20+
git --version       # Any recent version
```

**Installation commands (if missing):**

```bash
# macOS (using Homebrew)
brew install node python@3.11 docker git

# Ubuntu/Debian
sudo apt update
sudo apt install nodejs python3.11 docker.io git

# Windows (using winget)
winget install OpenJS.NodeJS Python.Python.3.11 Docker.DockerDesktop Git.Git
```

### Install Claude Code

```bash
# Option 1: npm (recommended)
npm install -g @anthropic-ai/claude-code

# Option 2: Homebrew (macOS)
brew install claude-code

# Verify installation
claude --version
```

### First-Time Authentication

```bash
# Start Claude Code - it will open browser for login
claude

# You'll see:
# "Opening browser to authenticate..."
# Log in with your Claude Pro/Max account
```

---

## API Keys Setup

### 1. Anthropic API Key (Required)

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Navigate to **API Keys**
3. Click **Create Key**
4. Name it `cbi-development`
5. Copy and save securely

```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
export ANTHROPIC_API_KEY="sk-ant-api03-your-key-here"
```

### 2. Create Telegram Bot (Required for MVP)

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Name: `CBI Health Reporter` (or your choice)
4. Username: `cbi_health_bot` (must be unique, end with `bot`)
5. Save the token BotFather gives you

```bash
# Add to your shell profile
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
```

### 3. Generate Security Keys

```bash
# Generate JWT secret (copy the output)
openssl rand -hex 32

# Generate encryption key (copy the output)
openssl rand -hex 32

# Generate phone hash salt (copy the output)
openssl rand -hex 16
```

Add these to your environment:
```bash
export JWT_SECRET="your-generated-jwt-secret"
export ENCRYPTION_KEY="your-generated-encryption-key"
export PHONE_HASH_SALT="your-generated-salt"
```

---

## Project Setup

### 1. Create Project Directory

```bash
mkdir community-based-intelligence
cd community-based-intelligence
git init
```

### 2. Copy Configuration Files

After running through this guide, your project should have:

```
community-based-intelligence/
├── CLAUDE.md                    # Project context (Claude Code reads this)
├── QUICKSTART.md               # This file
├── IMPLEMENTATION_GUIDE.md     # Phased prompts
├── .claude/
│   └── commands/
│       ├── implement-feature.md
│       ├── review.md
│       └── add-tests.md
├── .env.example                # Environment template
└── .gitignore
```

### 3. Create .env.example

```bash
cat > .env.example << 'EOF'
# Application
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://cbi:password@localhost:5432/cbi

# Redis
REDIS_URL=redis://localhost:6379

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook/telegram

# WhatsApp (for production - leave empty for MVP)
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_VERIFY_TOKEN=

# Security
JWT_SECRET=your-256-bit-secret
JWT_EXPIRE_HOURS=24
ENCRYPTION_KEY=your-32-byte-key
ENCRYPTION_SALT=your-salt
PHONE_HASH_SALT=your-phone-salt

# CORS
CORS_ORIGINS=["http://localhost:3000"]
EOF
```

### 4. Create .gitignore

```bash
cat > .gitignore << 'EOF'
# Environment
.env
.env.local
*.env

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/

# Node
node_modules/
.next/
dist/

# IDE
.vscode/
.idea/
*.swp

# Docker
docker-compose.override.yml

# Logs
*.log
logs/

# Database
*.db
*.sqlite

# OS
.DS_Store
Thumbs.db
EOF
```

---

## Verify Your Setup

Run this checklist before starting development:

```bash
# 1. Claude Code works
claude --version
# Expected: Shows version number

# 2. Environment variables are set
echo $ANTHROPIC_API_KEY
# Expected: Shows your API key (starts with sk-ant-)

echo $TELEGRAM_BOT_TOKEN
# Expected: Shows your bot token

# 3. Docker is running
docker ps
# Expected: No errors (may show empty list)

# 4. You're in the project directory with CLAUDE.md
ls CLAUDE.md
# Expected: Shows the file

# 5. Start Claude Code
claude
# Expected: Opens interactive session, shows welcome message
```

---

## Troubleshooting

### "Claude Code not found"
```bash
# Check npm global path
npm config get prefix
# Add to PATH if needed:
export PATH="$(npm config get prefix)/bin:$PATH"
```

### "Authentication failed"
```bash
# Clear credentials and re-authenticate
rm -rf ~/.claude
claude  # Will prompt for login again
```

### "API key invalid"
- Verify key at [console.anthropic.com](https://console.anthropic.com)
- Ensure no extra spaces when copying
- Check you have credits/subscription active

### "Docker connection refused"
```bash
# macOS/Windows: Start Docker Desktop application
# Linux:
sudo systemctl start docker
sudo usermod -aG docker $USER  # Then log out/in
```

### "Permission denied" errors
```bash
# Fix npm permissions
sudo chown -R $(whoami) ~/.npm
sudo chown -R $(whoami) /usr/local/lib/node_modules
```

### "Telegram webhook not working"
- For local development, you need ngrok or similar tunnel
- The webhook URL must be HTTPS
- Bot token must match exactly

---

## Next Steps

Once everything is verified:

1. **Read `CLAUDE.md`** - Understand the project context Claude Code will use
2. **Open `IMPLEMENTATION_GUIDE.md`** - Start with Phase 1
3. **Start Claude Code**: `claude` in your project directory
4. **Copy prompts** from the implementation guide and paste into Claude Code

**Pro Tips:**
- Use `/clear` between major phases to reset context
- Use `@filename` to reference specific files
- Press `Escape` twice to see message history
- Use `/help` to see all available commands
