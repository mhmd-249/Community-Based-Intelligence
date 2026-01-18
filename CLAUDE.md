# CBI - Community Based Intelligence

> Multi-Agent Health Surveillance System for Sudan

## Project Overview

CBI is a three-agent AI system that enables community members to report health incidents via messaging platforms (Telegram MVP, WhatsApp production). Reports are collected through natural conversation, classified using epidemiological frameworks, and routed to health officers via a web dashboard.

**Core Problem:** Sudan has a severe shortage of health officers to receive and process community health reports. One officer can only handle one phone call at a time, creating bottlenecks that delay outbreak response.

**Solution:** AI agents that can simultaneously handle many conversations, extract structured data from natural language, and provide health officers with actionable intelligence.

---

## Technology Stack

### Backend
| Component | Technology | Version/Notes |
|-----------|------------|---------------|
| **LLM (Reporter)** | Claude 3.5 Haiku | Fast, cost-effective, excellent Arabic |
| **LLM (Surveillance/Analyst)** | Claude 3.5 Sonnet | Superior reasoning for classification |
| **Agent Orchestration** | LangGraph | Explicit state machines, production-ready |
| **Database** | PostgreSQL + PostGIS | Geospatial queries for outbreak mapping |
| **Cache/Queue** | Redis + Redis Streams | State, sessions, message queue |
| **API Framework** | FastAPI | Async-native, OpenAPI docs |
| **Messaging (MVP)** | Telegram Bot API | Free, instant setup |
| **Messaging (Prod)** | WhatsApp Business API | Primary channel in Sudan |
| **Cloud** | AWS | ECS Fargate, RDS, ElastiCache |

### Frontend (Dashboard)
| Component | Technology | Version/Notes |
|-----------|------------|---------------|
| **Framework** | Next.js 14 | App Router, Server Components |
| **Language** | TypeScript | Type-safe JavaScript |
| **Styling** | Tailwind CSS | Utility-first CSS |
| **Components** | shadcn/ui | Accessible, customizable |
| **State (Server)** | React Query | Server state management |
| **State (Client)** | Zustand | Lightweight client state |
| **Real-time** | Socket.io | WebSocket for live updates |
| **Charts** | Recharts | Data visualization |
| **Maps** | React Leaflet | Interactive incident maps |
| **Icons** | Lucide React | Consistent iconography |

---

## Architecture

### System Flow

```
Community Member → Telegram/WhatsApp → Webhook Handler → Redis Stream
                                                              ↓
Health Officer ← Dashboard ← Notifications ← Surveillance Agent ← Reporter Agent
                                   ↑                                    ↓
                            Analyst Agent ← Threshold Exceeded? ← Classification
```

### Three Agents

**1. Reporter Agent (Claude Haiku)**
- Handles all incoming conversations
- Detects health signals through natural language (NOT keyword matching)
- Collects MVS (Minimum Viable Signal): What, Where, When, Who
- Empathetic but concise tone
- Languages: Arabic and English (auto-detect)

**2. Surveillance Agent (Claude Sonnet)**
- Classifies reports by disease type and urgency
- Links related cases (geographic + temporal + symptom proximity)
- Monitors MoH thresholds
- Generates notifications for health officers

**3. Analyst Agent (Claude Sonnet)**
- Natural language database queries
- Generates visualizations
- Creates situation summaries when thresholds exceeded

### Operating Modes (Reporter Agent)

```
LISTENING MODE (default)
    ↓ Health signal detected
INVESTIGATING MODE (collect MVS)
    ↓ Data collected
CONFIRMING MODE (summarize for user)
    ↓ User confirms
COMPLETE → Handoff to Surveillance Agent
```

---

## Database Schema

### Core Tables

```sql
-- reporters: Community members (minimal PII)
reporters (
    id UUID PRIMARY KEY,
    phone_hash VARCHAR(64) UNIQUE,      -- SHA-256 for lookups
    phone_encrypted BYTEA,               -- AES-256 for retrieval
    preferred_language VARCHAR(2),
    total_reports INTEGER
)

-- reports: Health incident reports
reports (
    id UUID PRIMARY KEY,
    reporter_id UUID REFERENCES reporters,
    officer_id UUID REFERENCES officers,
    conversation_id VARCHAR(100),
    status ENUM('open','investigating','resolved','false_alarm'),
    
    -- MVS Data
    symptoms TEXT[],
    suspected_disease ENUM('cholera','dengue','malaria','unknown'),
    location_text TEXT,
    location_normalized VARCHAR(200),
    location_point GEOGRAPHY(POINT, 4326),  -- PostGIS
    onset_text TEXT,
    onset_date DATE,
    cases_count INTEGER,
    deaths_count INTEGER,
    
    -- Classification
    urgency ENUM('critical','high','medium','low'),
    alert_type ENUM('suspected_outbreak','cluster','single_case','rumor'),
    data_completeness FLOAT,
    
    -- Metadata
    raw_conversation JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

-- officers: Health officers
officers (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    name VARCHAR(255),
    region VARCHAR(100),
    role VARCHAR(50)
)

-- notifications: Alerts for officers
notifications (
    id UUID PRIMARY KEY,
    report_id UUID REFERENCES reports,
    officer_id UUID REFERENCES officers,
    urgency ENUM,
    title TEXT,
    body TEXT,
    channels TEXT[],
    sent_at TIMESTAMP,
    read_at TIMESTAMP
)

-- report_links: Case clustering
report_links (
    report_id_1 UUID,
    report_id_2 UUID,
    link_type ENUM('geographic','temporal','symptom','manual'),
    confidence FLOAT
)
```

---

## Disease Thresholds (Ministry of Health)

| Disease | Alert Threshold | Outbreak Threshold | Window |
|---------|----------------|-------------------|--------|
| Cholera | 1 case | 3+ cases | 7 days |
| Dengue | 5 cases/week | 20+ cases/week | 7 days |
| Malaria | Above baseline | Significant deviation | Seasonal |
| Clustered Deaths | 2+ unexplained | 5+ | 7 days |

---

## Project Structure

```
cbi/
├── api/
│   ├── main.py              # FastAPI application
│   ├── deps.py              # Dependency injection
│   ├── middleware.py        # Rate limiting, logging
│   ├── routes/
│   │   ├── webhook.py       # Telegram/WhatsApp webhooks
│   │   ├── reports.py       # Reports CRUD
│   │   ├── notifications.py # Notifications
│   │   ├── analytics.py     # Analyst queries
│   │   └── auth.py          # Authentication
│   └── schemas/             # Pydantic models
│
├── agents/
│   ├── state.py             # ConversationState TypedDict
│   ├── graph.py             # LangGraph workflow
│   ├── reporter.py          # Reporter Agent
│   ├── surveillance.py      # Surveillance Agent
│   ├── analyst.py           # Analyst Agent
│   └── prompts.py           # System prompts
│
├── services/
│   ├── state.py             # Redis state management
│   ├── crypto.py            # Phone encryption/hashing
│   ├── auth.py              # JWT handling
│   ├── message_queue.py     # Redis Streams
│   └── messaging/
│       ├── base.py          # Abstract gateway
│       ├── telegram.py      # Telegram implementation
│       ├── whatsapp.py      # WhatsApp implementation
│       └── factory.py       # Gateway factory
│
├── db/
│   ├── session.py           # Database connection
│   ├── models.py            # SQLAlchemy models
│   └── queries.py           # Database queries
│
├── workers/
│   └── main.py              # Background worker entry
│
├── config/
│   ├── settings.py          # Pydantic settings
│   ├── llm_config.py        # LLM configurations
│   └── logging.py           # Structured logging
│
├── migrations/              # SQL migrations
├── tests/                   # Test suites
├── dashboard/               # Next.js frontend
│   ├── src/
│   │   ├── app/             # App Router pages
│   │   │   ├── (auth)/      # Auth pages (login)
│   │   │   ├── (dashboard)/ # Protected dashboard pages
│   │   │   ├── layout.tsx   # Root layout
│   │   │   └── providers.tsx
│   │   ├── components/
│   │   │   ├── ui/          # shadcn components
│   │   │   ├── layout/      # Sidebar, Header
│   │   │   ├── dashboard/   # Stats, alerts
│   │   │   ├── reports/     # Table, filters
│   │   │   ├── map/         # Leaflet map
│   │   │   ├── charts/      # Recharts
│   │   │   └── notifications/
│   │   ├── hooks/           # React Query hooks
│   │   ├── lib/             # API client, utils
│   │   ├── stores/          # Zustand stores
│   │   └── types/           # TypeScript types
│   └── public/sounds/       # Alert sounds
├── terraform/               # AWS infrastructure
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

---

## Coding Standards

### Python (Backend)
- Python 3.11+
- Type hints required on all functions
- Async/await for I/O operations
- Pydantic for data validation
- Use `"""docstrings"""` for public functions

### TypeScript (Frontend)
- Strict mode enabled
- Explicit return types on functions
- Interface over type for object shapes
- Use React Query for server state
- Use Zustand for client state
- Prefer Server Components where possible

### Naming Conventions
- Python files: `snake_case.py`
- TypeScript files: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- Classes/Components: `PascalCase`
- Functions/variables: `snake_case` (Python), `camelCase` (TypeScript)
- Constants: `UPPER_SNAKE_CASE`
- Database columns: `snake_case`
- API responses: `camelCase` (converted from snake_case)

### Error Handling
- Custom exceptions in `exceptions.py`
- Always log errors with context
- Never expose internal errors to users
- Graceful degradation for LLM failures

### Security Requirements
- NEVER log phone numbers or PII
- Hash phone numbers for lookups (SHA-256)
- Encrypt phone numbers for storage (AES-256)
- Validate all webhook signatures
- JWT for dashboard authentication
- Rate limit all endpoints

---

## LLM Configuration

### Reporter Agent (Haiku)
```python
{
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 500,
    "temperature": 0.3,  # Low for consistency
    "timeout": 30.0
}
```

### Surveillance/Analyst Agent (Sonnet)
```python
{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 2000,  # 4000 for Analyst
    "temperature": 0.1,  # Very low for classification
    "timeout": 60.0      # 120 for Analyst
}
```

---

## Key Design Decisions

1. **LLM Intent Detection over Keywords**: Use Claude's understanding to detect health signals, not regex/keyword matching. This handles natural conversation flow.

2. **Flexible Data Collection**: Accept partial/vague information. Any data is better than blocking stressed reporters with rigid forms.

3. **Messaging Gateway Abstraction**: Abstract Telegram/WhatsApp behind common interface for easy platform switching.

4. **Redis Streams for Queue**: Simpler than Kafka, sufficient for MVP scale (~2000 messages/day).

5. **PostGIS for Geospatial**: Enable proximity-based case linking and outbreak mapping.

6. **Conversation State in Redis**: Fast access, TTL-based cleanup, survives disconnections.

---

## Commands

```bash
# Development
docker-compose up -d          # Start all services
uvicorn api.main:app --reload # Run API server
python -m workers.main        # Run background worker

# Testing
pytest                        # Run all tests
pytest tests/agents/          # Run agent tests only
pytest -k "test_intent"       # Run specific tests

# Database
alembic upgrade head          # Run migrations
alembic revision -m "desc"    # Create migration

# Linting
ruff check .                  # Lint Python
ruff format .                 # Format Python
mypy .                        # Type checking
```

---

## Environment Variables

Required:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `ANTHROPIC_API_KEY` - Claude API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `JWT_SECRET` - 256-bit secret for JWT
- `ENCRYPTION_KEY` - 32-byte key for AES
- `PHONE_HASH_SALT` - Salt for phone hashing

See `.env.example` for complete list.

---

## Testing Approach

1. **Unit Tests**: Pure functions, utilities (~200 tests)
2. **Integration Tests**: DB queries, API endpoints (~100 tests)
3. **Agent Tests**: Agent nodes with mocked LLM (~50 tests)
4. **E2E Tests**: Full message flow simulation (~20 tests)

Golden dataset for intent detection includes cases that SHOULD and SHOULD NOT trigger investigation mode.

---

## Important Notes for Development

- Always test Arabic language support alongside English
- Reporter Agent responses should be under 50 words
- Conversation tone: empathetic but concise, never verbose
- Critical reports must generate notifications within 6 hours
- All database operations must use async
- Phone numbers are sensitive PII - hash for lookups, encrypt for storage
