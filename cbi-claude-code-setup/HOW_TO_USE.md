# How to Use This CBI Development Kit

This guide explains how to use the files in this package to build the CBI system with Claude Code.

---

## Quick Start (5 minutes)

```bash
# 1. Create your project directory
mkdir community-based-intelligence
cd community-based-intelligence

# 2. Copy all files from this package
cp -r /path/to/cbi-claude-code-setup/* .
cp -r /path/to/cbi-claude-code-setup/.claude .

# 3. Verify structure
ls -la
# Should show: CLAUDE.md, QUICKSTART.md, IMPLEMENTATION_GUIDE.md, .claude/

# 4. Complete prerequisites from QUICKSTART.md
# (API keys, accounts, software installation)

# 5. Start Claude Code
claude
```

---

## Project Structure After Setup

```
community-based-intelligence/
├── CLAUDE.md                      # ⭐ Project context (Claude reads this automatically)
├── QUICKSTART.md                  # Prerequisites checklist
├── IMPLEMENTATION_GUIDE.md        # Phased prompts to copy-paste
├── HOW_TO_USE.md                  # This file
├── .claude/
│   └── commands/
│       ├── implement-feature.md   # /project:implement-feature
│       ├── review.md              # /project:review
│       └── add-tests.md           # /project:add-tests
├── .env.example                   # Create this from QUICKSTART.md
└── .gitignore                     # Create this from QUICKSTART.md
```

---

## Understanding the Files

### CLAUDE.md (Most Important!)
This is the "memory" file that Claude Code reads automatically when you start a session in this directory. It contains:
- Project architecture overview
- Technology stack decisions
- Database schema
- Coding standards
- LLM configuration
- Project structure

**Claude Code uses this to understand your project context.** Keep it updated as you make architectural decisions.

### QUICKSTART.md
A checklist to ensure you have everything ready:
- Required accounts (Anthropic, Telegram, AWS, etc.)
- Software to install (Node, Python, Docker)
- API keys to generate
- Initial project setup commands

**Complete this ONCE before starting development.**

### IMPLEMENTATION_GUIDE.md
Contains phased prompts you copy-paste into Claude Code:
- **Phase 1:** Project Foundation (structure, Docker, database)
- **Phase 2:** Messaging Gateway (Telegram/WhatsApp abstraction)
- **Phase 3:** Reporter Agent (conversation handling)
- **Phase 4:** Surveillance Agent (classification, alerts)
- **Phase 5:** Dashboard Backend (API, auth, WebSocket)
- **Phase 6:** Analyst Agent (queries, visualizations)
- **Phase 7:** Testing (unit, integration, E2E)
- **Phase 8:** Production Deployment (AWS, monitoring)

**Work through phases sequentially. Each builds on the previous.**

### .claude/commands/
Custom slash commands for ongoing development:

| Command | Purpose | Usage |
|---------|---------|-------|
| `/project:implement-feature` | Implement new feature with tests | `/project:implement-feature Add voice note transcription` |
| `/project:review` | Code review for issues | `/project:review @agents/reporter.py` |
| `/project:add-tests` | Generate tests for code | `/project:add-tests @services/state.py` |

---

## Daily Development Workflow

### Starting a Session

```bash
cd community-based-intelligence
claude
```

Claude Code automatically reads `CLAUDE.md` and understands your project.

### Implementing Features

1. **For new phases:** Copy prompt from `IMPLEMENTATION_GUIDE.md`
2. **For new features:** Use `/project:implement-feature [description]`
3. **For bug fixes:** Describe the bug and ask Claude to fix it

### Reviewing Code

```
/project:review @agents/reporter.py @agents/surveillance.py
```

### Adding Tests

```
/project:add-tests @services/notifications.py
```

### Useful Commands Inside Claude Code

| Command | What it does |
|---------|--------------|
| `/help` | Show all available commands |
| `/clear` | Clear conversation history (use between phases) |
| `@filename` | Reference a specific file |
| `!command` | Run shell command (e.g., `!pytest`) |
| `Escape` | Stop current generation |
| `Escape Escape` | Show message history |

---

## Tips for Best Results

### 1. Work in Phases
Don't try to build everything at once. Follow the phases in order:
```
Phase 1 → Phase 2 → Phase 3 → ... → Phase 8
```

### 2. Use /clear Between Phases
This resets the conversation context, preventing confusion:
```
[Complete Phase 1]
/clear
[Start Phase 2]
```

### 3. Review Before Proceeding
After each prompt, review the generated code:
- Does it match the architecture?
- Are there any errors?
- Run `!ruff check .` to lint

### 4. Test Incrementally
Run tests after each phase:
```
!pytest tests/unit/
!pytest tests/integration/
```

### 5. Use @file References for Follow-ups
If you need to modify or discuss specific files:
```
Can you add error handling to @agents/reporter.py for the case when the Anthropic API times out?
```

### 6. Ask for Explanations
If you don't understand something:
```
Can you explain what the LangGraph conditional edges do in @agents/graph.py?
```

### 7. Handle Large Files
If Claude generates a partial file, say:
```
continue
```
or
```
finish implementing the remaining functions
```

### 8. Version Control Often
Commit after each successful phase:
```bash
git add .
git commit -m "Phase 3: Reporter Agent complete"
```

---

## Troubleshooting

### "Claude doesn't understand my project"
- Make sure `CLAUDE.md` exists in your current directory
- Check you're in the right directory when starting `claude`

### "Output is incomplete"
- Say "continue" to get the rest
- Or ask specifically: "finish the surveillance_node function"

### "Claude made mistakes"
- Point out the specific issue
- Reference the relevant section of CLAUDE.md
- Ask for correction: "This doesn't match our database schema. The reports table should have..."

### "Context seems confused"
- Use `/clear` to reset
- Restart with fresh context: `claude --resume` shows recent sessions

### "Custom commands not showing"
- Verify `.claude/commands/` directory exists
- Check files end in `.md`
- Restart Claude Code

### "Need to see what's in a file"
- Use `@filename` to reference it
- Or ask: "Show me the contents of agents/state.py"

---

## Example Development Session

```
$ cd community-based-intelligence
$ claude

Claude Code v1.2.0

> /clear

> [Paste prompt from IMPLEMENTATION_GUIDE.md Phase 1.1]

[Claude generates project structure...]

> The pyproject.toml looks good. Can you also add a Makefile with common commands?

[Claude generates Makefile...]

> !make lint

[Runs linting...]

> There's a linting error in config/settings.py line 23. Please fix it.

[Claude fixes the error...]

> @config/settings.py looks good now. Let's move to Docker setup.

> [Paste prompt from IMPLEMENTATION_GUIDE.md Phase 1.2]

[Claude generates Docker configuration...]

> !docker-compose up -d

[Starts services...]

> Great, all services are running. Let's commit this and continue to Phase 1.3.

> !git add . && git commit -m "Phase 1.1-1.2: Project structure and Docker"

> /clear

> [Paste prompt for Phase 1.3...]
```

---

## Getting Help

1. **Claude Code documentation:** [code.claude.com/docs](https://code.claude.com/docs)
2. **Anthropic support:** [support.anthropic.com](https://support.anthropic.com)
3. **Ask Claude Code itself:** It can explain its own features

---

## What's Next?

1. ✅ Read through `QUICKSTART.md` and complete prerequisites
2. ✅ Set up your environment variables
3. ✅ Start Claude Code in your project directory
4. ✅ Begin with Phase 1 in `IMPLEMENTATION_GUIDE.md`
5. 🚀 Build CBI!

Good luck building the Community Based Intelligence system!
