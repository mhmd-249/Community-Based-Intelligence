# CBI - Community Based Intelligence

> Multi-Agent Health Surveillance System for Sudan

CBI is a three-agent AI system that enables community members to report health incidents via messaging platforms. Reports are collected through natural conversation, classified using epidemiological frameworks, and routed to health officers via a web dashboard.

## The Problem

Sudan has a severe shortage of health officers to receive and process community health reports. One officer can only handle one phone call at a time, creating bottlenecks that delay outbreak response.

## The Solution

AI agents that can simultaneously handle many conversations, extract structured data from natural language, and provide health officers with actionable intelligence.

## Architecture

```
Community Member → Telegram/WhatsApp → Webhook Handler → Redis Stream
                                                              ↓
Health Officer ← Dashboard ← Notifications ← Surveillance Agent ← Reporter Agent
                                   ↑                                    ↓
                            Analyst Agent ← Threshold Exceeded? ← Classification
```

### Three Agents

| Agent | Model | Purpose |
|-------|-------|---------|
| **Reporter** | Claude 3.5 Haiku | Handles conversations, detects health signals, collects MVS data |
| **Surveillance** | Claude 3.5 Sonnet | Classifies reports, links cases, monitors thresholds |
| **Analyst** | Claude 3.5 Sonnet | Natural language queries, visualizations, situation summaries |

## Tech Stack

**Backend:** FastAPI, LangGraph, PostgreSQL + PostGIS, Redis, Anthropic Claude

**Frontend:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, React Query

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Node.js 20+ (for dashboard development)
- Anthropic API key
- Telegram Bot Token (for MVP)
- ngrok account (for webhook tunneling)

## Quick Start

1. **Clone and configure environment**

```bash
git clone https://github.com/your-org/Community_Based_Intelligence.git
cd Community_Based_Intelligence
cp .env.example .env
```

2. **Edit `.env` with your credentials**

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-xxxxx
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
JWT_SECRET=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 16)
PHONE_HASH_SALT=$(openssl rand -hex 16)
NGROK_AUTHTOKEN=your-ngrok-token
```

3. **Start all services**

```bash
docker-compose up -d
```

4. **View service status**

```bash
docker-compose ps
```

5. **Get your webhook URL**

Open http://localhost:4040 to see the ngrok tunnel URL, then configure it in Telegram BotFather.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| API | http://localhost:8000 | FastAPI backend |
| API Docs | http://localhost:8000/docs | OpenAPI documentation |
| Dashboard | http://localhost:3000 | Health officer dashboard |
| ngrok | http://localhost:4040 | Webhook tunnel status |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache and message queue |

## Project Structure

```
cbi/
├── api/                 # FastAPI application
│   ├── routes/          # API endpoints
│   └── schemas/         # Pydantic models
├── agents/              # LangGraph agents
├── services/            # Business logic
│   └── messaging/       # Telegram/WhatsApp gateways
├── db/                  # Database models and queries
├── workers/             # Background processors
└── config/              # Settings and logging

dashboard/               # Next.js frontend
migrations/              # Alembic database migrations
tests/                   # Test suites
scripts/                 # Utility scripts
```

## Development

### Running locally (without Docker)

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start API server
uvicorn cbi.api.main:app --reload

# Start background worker
python -m cbi.workers.main
```

### Running tests

```bash
pytest                        # All tests
pytest tests/agents/          # Agent tests only
pytest -k "test_intent"       # Specific tests
pytest --cov=cbi              # With coverage
```

### Code quality

```bash
ruff check .                  # Lint
ruff format .                 # Format
mypy .                        # Type check
```

### Database migrations

```bash
alembic revision -m "description"   # Create migration
alembic upgrade head                # Apply migrations
alembic downgrade -1                # Rollback one
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `JWT_SECRET` | Yes | 256-bit secret for JWT signing |
| `ENCRYPTION_KEY` | Yes | 32-byte AES encryption key |
| `PHONE_HASH_SALT` | Yes | Salt for phone number hashing |
| `NGROK_AUTHTOKEN` | No | ngrok authentication token |
| `ENVIRONMENT` | No | development/staging/production |

See `.env.example` for the complete list.

## Security

- Phone numbers are hashed (SHA-256) for lookups and encrypted (AES-256) for storage
- PII is never logged
- All webhook signatures are validated
- JWT authentication for dashboard
- Rate limiting on all endpoints

## Disease Thresholds

| Disease | Alert | Outbreak | Window |
|---------|-------|----------|--------|
| Cholera | 1 case | 3+ cases | 7 days |
| Dengue | 5/week | 20+/week | 7 days |
| Malaria | Above baseline | Significant deviation | Seasonal |
| Clustered Deaths | 2+ unexplained | 5+ | 7 days |

## License

MIT
