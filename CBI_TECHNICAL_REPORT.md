# CBI Technical Report — Community Based Intelligence

> Comprehensive architecture and implementation analysis for interview preparation.
> Generated from actual source code analysis — not documentation or plans.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Deep Dive](#2-architecture-deep-dive)
3. [Technology Stack Justification](#3-technology-stack-justification)
4. [Backend Architecture](#4-backend-architecture)
5. [Agent System (LangGraph)](#5-agent-system-langgraph)
6. [Database Design](#6-database-design)
7. [Messaging Gateway Abstraction](#7-messaging-gateway-abstraction)
8. [State Management (Redis)](#8-state-management-redis)
9. [Real-time System](#9-real-time-system)
10. [Frontend Dashboard](#10-frontend-dashboard)
11. [Security Architecture](#11-security-architecture)
12. [Testing Strategy](#12-testing-strategy)
13. [DevOps & Deployment](#13-devops--deployment)
14. [Key Design Decisions & Tradeoffs](#14-key-design-decisions--tradeoffs)
15. [Scalability Considerations](#15-scalability-considerations)
16. [Challenges & Solutions](#16-challenges--solutions)

---

## 1. Project Overview

### Problem Statement

Sudan has a severe shortage of health officers who receive and process community health reports. A single officer can only handle one phone call at a time, creating critical bottlenecks that delay outbreak response. The country's health surveillance infrastructure needs a force-multiplier that can process many conversations simultaneously and produce structured, actionable intelligence.

### Solution

CBI is a three-agent AI system that enables community members to report health incidents via messaging platforms (Telegram for MVP, WhatsApp for production). Reports are collected through natural conversation in Arabic and English, classified using epidemiological frameworks from Sudan's Ministry of Health (MoH), and routed to health officers via a real-time web dashboard.

### Core Value Proposition

- **Scale**: AI agents handle unlimited concurrent conversations vs. one call per officer
- **Speed**: Automated classification and threshold checking triggers notifications within minutes
- **Structure**: Natural language is converted into structured data (disease, location, urgency, case counts)
- **Intelligence**: Geographic and temporal case linking enables early outbreak detection

### Current Implementation Status

| Component | Status |
|-----------|--------|
| Reporter Agent (conversation) | Fully implemented |
| Surveillance Agent (classification) | Fully implemented |
| Analyst Agent (NL queries + visualizations) | Fully implemented |
| Telegram Gateway | Fully implemented |
| WhatsApp Gateway | Implemented (structure complete, webhook handler is placeholder) |
| Redis State Management | Fully implemented |
| Redis Streams Message Queue | Fully implemented |
| Worker (background processor) | Fully implemented |
| Dashboard (Next.js) | Fully implemented |
| Real-time WebSocket notifications | Fully implemented |
| PostGIS geospatial queries | Fully implemented |
| Webhook handler (legacy route) | Placeholder — returns `{"status": "received"}` |

---

## 2. Architecture Deep Dive

### System Flow (End-to-End)

```
Community Member
    │  Sends message via Telegram/WhatsApp
    ▼
Webhook Handler (FastAPI)
    │  Parses platform-specific payload → IncomingMessage
    │  Queues to Redis Stream (cbi:messages:incoming)
    ▼
Background Worker
    │  Consumes from Redis Stream via consumer group
    │  Loads/creates ConversationState from Redis
    │  Adds user message to state
    ▼
LangGraph Pipeline
    ├─→ Reporter Node
    │       Calls Claude Sonnet (temp=0.3, 500 tokens)
    │       Detects health signals, collects MVS data
    │       Sets pending_response
    │
    ├─→ send_response Node
    │       Sends response to user via MessagingGateway
    │       Clears pending_response
    │
    ├─→ Surveillance Node (if conversation complete)
    │       Calls Claude Sonnet (temp=0.1, 2000 tokens)
    │       Classifies disease, checks MoH thresholds
    │       Creates Report in PostgreSQL/PostGIS
    │       Links related cases (geographic + temporal + symptom)
    │
    ├─→ Analyst Node (if urgency = critical/high)
    │       Generates situation summary
    │
    └─→ send_notification Node (if urgency >= medium)
            Creates Notification records for all officers
            Broadcasts via Redis pub/sub → WebSocket
    ▼
Dashboard (Next.js)
    │  Health officers view reports, maps, analytics
    │  Real-time alerts via WebSocket
    └─→ Officers update report status, add investigation notes
```

### Component Interaction Diagram

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Telegram   │     │   WhatsApp   │     │   Dashboard   │
│   Bot API    │     │ Business API │     │   (Next.js)   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI Application                     │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌────────┐ │
│  │ Webhook │  │  Reports  │  │ Analytics  │  │  Auth  │ │
│  │ Routes  │  │   CRUD    │  │  Routes    │  │ Routes │ │
│  └────┬────┘  └────┬─────┘  └─────┬──────┘  └───┬────┘ │
└───────┼────────────┼───────────────┼─────────────┼──────┘
        │            │               │             │
        ▼            ▼               ▼             ▼
┌───────────┐  ┌──────────┐  ┌────────────┐  ┌─────────┐
│  Redis    │  │ Postgres │  │  Analyst   │  │  JWT +  │
│  Stream   │  │ + PostGIS│  │  Agent     │  │  bcrypt │
└─────┬─────┘  └──────────┘  └────────────┘  └─────────┘
      │
      ▼
┌─────────────────────────────────┐
│      Background Worker          │
│  ┌─────────┐  ┌──────────────┐ │
│  │ Redis   │  │  LangGraph   │ │
│  │ State   │  │  Pipeline    │ │
│  │ Service │  │  (3 agents)  │ │
│  └─────────┘  └──────────────┘ │
└─────────────────────────────────┘
```

### Key Architectural Patterns

1. **Event-Driven Message Processing**: Webhook → Redis Stream → Worker decouples message reception from processing. The API responds to Telegram instantly while the worker processes asynchronously.

2. **Agent State Machine**: The LangGraph `StateGraph` implements an explicit state machine with conditional routing. State transitions are deterministic functions, not probabilistic LLM outputs.

3. **Separation of Concerns in Agents**: Reporter handles user interaction, Surveillance handles classification + DB persistence, Analyst handles officer-facing queries. They share state through `ConversationState` TypedDict but have no direct dependencies on each other.

4. **Graceful Degradation**: Every agent has error handlers that produce useful defaults rather than failing the pipeline. Surveillance failures still produce medium-urgency classifications for manual review. Reporter failures return localized apology messages.

---

## 3. Technology Stack Justification

### Backend

| Technology | Why This Choice | Alternatives Considered |
|-----------|----------------|------------------------|
| **Claude Sonnet** (all agents) | Superior Arabic NLU, structured JSON output, fast response times. All three agents use `claude-sonnet-4-5-20250929`. | GPT-4 (weaker Arabic), Llama (no Arabic fine-tuning), Gemini (less structured output) |
| **LangGraph** | Explicit state machines over opaque chains. Graph structure makes routing logic auditable and testable. Conditional edges are pure functions. | LangChain (too abstracted), CrewAI (less control), custom (too much boilerplate) |
| **FastAPI** | Async-native, auto-generated OpenAPI docs, Pydantic integration. Perfect for webhook handling + REST API. | Flask (no async), Django (too heavy), Starlette (lower-level) |
| **PostgreSQL + PostGIS** | Relational integrity for report/officer/notification data. PostGIS enables `ST_DWithin` spatial queries for geographic case linking within configurable radius. | MongoDB (no spatial joins), DynamoDB (no geospatial), SQLite (no PostGIS) |
| **Redis** | Triple-duty: conversation state (key-value with TTL), message queue (Streams with consumer groups), real-time events (pub/sub). One dependency instead of three. | RabbitMQ (extra infra), Kafka (overkill for ~2000 msg/day), Celery (heavier than needed) |
| **SQLAlchemy 2.0 (async)** | Type-safe ORM with `mapped_column` syntax, first-class async support, GeoAlchemy2 integration for PostGIS. | Tortoise ORM (less mature), raw asyncpg (no ORM), Prisma (JS only) |
| **Pydantic** | Data validation, settings management, JSON serialization. Used for `ExtractedData`, `Classification`, `Settings`, API schemas. | dataclasses (no validation), attrs (no JSON), marshmallow (separate schema) |

### Frontend

| Technology | Why This Choice |
|-----------|----------------|
| **Next.js 14** (App Router) | Server Components for initial load performance, file-based routing, API route proxying |
| **React Query** | Server state management with caching, refetching, and optimistic updates for reports/notifications |
| **Zustand** | Lightweight client state for auth tokens and notification preferences (vs. Redux boilerplate) |
| **Socket.io** | WebSocket with automatic reconnection for real-time notification delivery |
| **React Leaflet** | Open-source mapping (vs. Mapbox costs) for incident map with PostGIS data |
| **Recharts** | Composable chart components for disease trends, case distribution, and analytics |
| **shadcn/ui** | Accessible, customizable component library built on Radix UI primitives |
| **Tailwind CSS** | Utility-first CSS that avoids CSS-in-JS runtime costs, good for rapid dashboard development |

### Infrastructure

| Technology | Why This Choice |
|-----------|----------------|
| **Docker Compose** | Local development with all services (API, Worker, Dashboard, PostgreSQL, Redis, ngrok) |
| **Multi-stage Dockerfile** | Builder → Runtime → Development stages. Non-root user in production. |
| **ngrok** | Free tunnel for Telegram webhook during development (no public IP needed) |
| **AWS (planned)** | ECS Fargate (serverless containers), RDS (managed Postgres), ElastiCache (managed Redis) |

---

## 4. Backend Architecture

### Project Structure

```
cbi/
├── api/
│   ├── main.py              # FastAPI app, lifespan, CORS, routers
│   ├── deps.py              # Dependency injection
│   ├── middleware.py         # Rate limiting, logging
│   ├── routes/
│   │   ├── auth.py          # Login, refresh, logout, me
│   │   ├── reports.py       # CRUD, filters, status updates, export
│   │   ├── notifications.py # List, read, dismiss, count
│   │   ├── analytics.py     # NL queries via Analyst Agent
│   │   ├── webhook.py       # Legacy placeholder
│   │   ├── webhooks.py      # Telegram/WhatsApp webhook handlers
│   │   └── websocket.py     # WebSocket endpoint for real-time
│   └── schemas/             # Pydantic request/response models
├── agents/
│   ├── state.py             # ConversationState TypedDict + helpers
│   ├── graph.py             # LangGraph StateGraph + routing
│   ├── reporter.py          # Reporter Agent node
│   ├── surveillance.py      # Surveillance Agent node
│   ├── analyst.py           # Analyst Agent (queries + summaries)
│   └── prompts.py           # System prompts for all agents
├── services/
│   ├── state.py             # Redis StateService (conversation state)
│   ├── auth.py              # JWT + bcrypt + token blacklisting
│   ├── message_queue.py     # Redis Streams producer/consumer
│   ├── realtime.py          # Redis pub/sub for WebSocket
│   └── messaging/
│       ├── base.py          # Abstract MessagingGateway + dataclasses
│       ├── telegram.py      # Telegram Bot API implementation
│       ├── whatsapp.py      # WhatsApp Business API implementation
│       └── factory.py       # Singleton gateway factory
├── db/
│   ├── session.py           # Async engine + session management
│   ├── models.py            # SQLAlchemy 2.0 models
│   └── queries.py           # All database query functions
├── config/
│   ├── settings.py          # Pydantic Settings (env vars)
│   ├── llm_config.py        # Per-agent LLM configurations
│   └── logging.py           # structlog with PII filtering
├── workers/
│   ├── main.py              # Background Worker class
│   └── health.py            # Worker health endpoints (port 8081)
└── migrations/              # SQL schema migrations
```

### FastAPI Application Lifecycle

**File: `cbi/api/main.py`**

The FastAPI app uses an `asynccontextmanager` lifespan for startup/shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    configure_logging(json_format=settings.is_production)
    await init_db(pool_size=5, max_overflow=10, echo=settings.debug)
    redis_client = aioredis.from_url(settings.redis_url.get_secret_value())
    app.state.redis = redis_client

    # Backfill geocoding for existing reports
    async with get_session() as session:
        updated = await backfill_report_locations(session)
        await session.commit()

    yield

    # Shutdown
    await close_all_gateways()
    await redis_client.close()
    await close_db()
```

Key startup actions:
1. Configure structured logging (JSON for production, colored console for dev)
2. Initialize async database engine with connection pooling
3. Create Redis connection and store in `app.state`
4. Backfill geocoding for reports that have `location_text` but no `location_point`

### Router Registration

```python
app.include_router(auth.router, prefix="/api/auth")
app.include_router(reports.router, prefix="/api/reports")
app.include_router(notifications.router, prefix="/api/notifications")
app.include_router(analytics.router, prefix="/api/analytics")
app.include_router(webhook.router, prefix="/webhook")      # Legacy placeholder
app.include_router(webhooks.router)                         # Telegram/WhatsApp
app.include_router(websocket.router)                        # WebSocket
```

### CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Development allows `localhost:3000` (Next.js). Production disables CORS origins entirely (dashboard served from same domain or configured separately).

### Health Check

```python
@app.get("/health")
async def health_check():
    db_ok = await db_health_check()    # SELECT 1
    redis_ok = await app.state.redis.ping()
    return {"status": "healthy" if all_ok else "degraded", ...}
```

Reports `"degraded"` if either database or Redis is unreachable, not a hard failure. This is used by Docker healthchecks and load balancers.

### Settings Management

**File: `cbi/config/settings.py`**

Uses Pydantic `BaseSettings` with `@lru_cache` for singleton behavior:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr
    redis_url: SecretStr
    anthropic_api_key: SecretStr
    telegram_bot_token: SecretStr
    jwt_secret: SecretStr = Field(..., min_length=32)
    encryption_key: SecretStr
    phone_hash_salt: SecretStr

    @field_validator("database_url", mode="before")
    def validate_database_url(cls, v):
        # Auto-convert postgresql:// → postgresql+asyncpg://
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
```

All sensitive values use `SecretStr` to prevent accidental logging. The `database_url` validator transparently adds the `asyncpg` driver prefix so users can use standard PostgreSQL URLs.

### Background Worker

**File: `cbi/workers/main.py`**

The `Worker` class consumes from Redis Streams and processes through the LangGraph pipeline:

```python
class Worker:
    async def process_message(self, message: IncomingMessage):
        state_service = await get_state_service()
        state, is_new = await state_service.get_or_create_conversation(
            message.platform, message.from_id
        )
        state = add_message_to_state(state, MessageRole.user, message.text)

        graph = get_graph()
        result = await asyncio.wait_for(
            graph.ainvoke(state, config={"configurable": {"thread_id": conv_id}}),
            timeout=PROCESSING_TIMEOUT,  # 60 seconds
        )

        await state_service.save_state(result)
```

Key features:
- **Consumer groups**: Multiple workers can run in parallel without processing the same message twice
- **Pending message recovery**: On startup, processes unacknowledged messages first before new ones
- **60-second timeout**: Prevents hung LLM calls from blocking the worker indefinitely
- **WorkerMetrics**: Tracks success rate, average processing time, uptime
- **Signal handling**: SIGINT/SIGTERM trigger graceful shutdown
- **Health server**: Separate aiohttp server on port 8081 with `/health`, `/ready`, `/metrics` endpoints

---

## 5. Agent System (LangGraph)

This is the core of the system. The three agents are implemented as LangGraph nodes connected by conditional routing edges.

### ConversationState (Shared State Schema)

**File: `cbi/agents/state.py`**

```python
class ConversationState(TypedDict, total=False):
    # Identifiers
    conversation_id: str
    reporter_phone: str
    platform: str

    # Conversation history and mode
    messages: list[dict]           # [{role, content, timestamp, message_id}]
    current_mode: str              # listening|investigating|confirming|complete|error
    language: str                  # ar|en|unknown

    # Extracted data (MVS)
    extracted_data: dict           # ExtractedData model as dict

    # Classification (from Surveillance Agent)
    classification: dict           # Classification model as dict

    # Control flow
    pending_response: str | None   # Message to send to user
    handoff_to: str | None         # surveillance|analyst|human
    error: str | None

    # Metadata
    created_at: str
    updated_at: str
    turn_count: int
```

`total=False` is critical — it allows partial state updates in LangGraph. Each node only needs to return the fields it changes.

### Operating Modes (State Machine)

```
┌─────────────┐
│  LISTENING   │ ← Default. Normal conversation.
└──────┬──────┘
       │ Health signal detected
       ▼
┌─────────────┐
│INVESTIGATING │ ← Collecting MVS data
└──────┬──────┘
       │ Enough data collected
       ▼
┌─────────────┐
│ CONFIRMING   │ ← Summary shown, awaiting confirmation
└──────┬──────┘
       │ User confirms
       ▼
┌─────────────┐
│  COMPLETE    │ → Handoff to Surveillance
└─────────────┘
```

Mode transitions are determined by the Reporter Agent's LLM response (a `transition_to` field in the JSON), but the **mode validation** happens in code:

```python
if transition_to and transition_to != current_mode:
    new_mode = transition_to
    state = transition_mode(state, new_mode)

if new_mode == ConversationMode.complete.value:
    state = set_handoff(state, HandoffTarget.surveillance)
```

### MVS (Minimum Viable Signal) Data Model

**What**: symptoms, suspected_disease
**Where**: location_text, location_normalized, location_coords
**When**: onset_text, onset_date
**Who**: cases_count, deaths_count, affected_description, reporter_relationship

### Data Completeness Scoring

```python
MVS_FIELDS: dict[str, float] = {
    "symptoms":              0.25,  # What — most important
    "location_text":         0.25,  # Where — critical for response
    "onset_text":            0.20,  # When — timeline
    "cases_count":           0.15,  # Who — scale assessment
    "reporter_relationship": 0.10,  # Who — source credibility
    "affected_description":  0.05,  # Who — context
}
```

Weighted scoring means a report with symptoms + location is already 50% complete, which is enough to be useful. This reflects the design principle: **any data is better than none**.

### LangGraph Workflow

**File: `cbi/agents/graph.py`**

```python
def create_cbi_graph(checkpointer=None):
    workflow = StateGraph(ConversationState)

    # Nodes
    workflow.add_node("reporter", reporter_node)
    workflow.add_node("surveillance", surveillance_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("send_response", send_response_node)
    workflow.add_node("send_notification", send_notification_node)

    # Entry point
    workflow.set_entry_point("reporter")

    # Conditional routing
    workflow.add_conditional_edges("reporter", route_after_reporter,
        {"send_response": "send_response", "__end__": END})
    workflow.add_conditional_edges("send_response", route_after_send_response,
        {"surveillance": "surveillance", "__end__": END})
    workflow.add_conditional_edges("surveillance", route_after_surveillance,
        {"analyst": "analyst", "send_notification": "send_notification", "__end__": END})

    # Fixed edges
    workflow.add_edge("analyst", "send_notification")
    workflow.add_edge("send_notification", END)

    return workflow.compile(checkpointer=checkpointer or MemorySaver())
```

### Routing Logic (Pure Functions)

**`route_after_reporter`**:
- Error state → END
- Has `pending_response` → `send_response`
- Default → END

**`route_after_send_response`**:
- Mode = `complete` AND handoff = `surveillance` → `surveillance`
- Default → END (conversation still in progress, wait for next message)

**`route_after_surveillance`**:
- Urgency `critical` or `high` → `analyst` (for situation summary)
- Urgency `medium` → `send_notification` (skip analyst)
- Urgency `low` → END (no notification needed)

**Visual flow for a complete report with critical urgency**:
```
reporter → send_response → surveillance → analyst → send_notification → END
```

**Visual flow for a normal conversation turn (still collecting data)**:
```
reporter → send_response → END
```

### Reporter Agent

**File: `cbi/agents/reporter.py`**

**LLM Config**: Claude Sonnet, 500 tokens, temperature 0.3, 30s timeout

The reporter agent is the user-facing conversational interface. It:

1. **Detects language** using Unicode character analysis (not an LLM call):
   ```python
   ARABIC_CHAR_THRESHOLD = 0.3

   def detect_language(text: str) -> str:
       arabic_count = 0
       total_letters = 0
       for char in text:
           if unicodedata.category(char).startswith("L"):
               total_letters += 1
               if "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f":
                   arabic_count += 1
       return "ar" if (arabic_count / total_letters) >= 0.3 else "en"
   ```

2. **Formats system prompt** with current state (mode, language, extracted data, missing fields)

3. **Calls Claude** with full conversation history:
   ```python
   response = await client.messages.create(
       model=config.model,         # claude-sonnet-4-5-20250929
       max_tokens=config.max_tokens,  # 500
       temperature=config.temperature, # 0.3
       system=system_prompt,
       messages=message_history,
   )
   ```

4. **Parses JSON response** with three-level fallback:
   ```python
   def parse_json_response(response_text):
       # 1. Extract from ```json ... ``` code blocks
       # 2. Try parsing entire response as JSON
       # 3. Find any {...} in the response
       # Falls back to using raw text as response
   ```

5. **Merges extracted data** (symptoms are deduplicated via `dict.fromkeys`):
   ```python
   if isinstance(value, list) and len(value) > 0:
       existing = current_data.get(key, [])
       combined = list(dict.fromkeys(existing + value))
       updates[key] = combined
   ```

6. **Handles errors** with localized messages:
   ```python
   ERROR_MESSAGES = {
       "en": "I'm sorry, I'm having trouble processing your message...",
       "ar": "عذراً، أواجه مشكلة في معالجة رسالتك...",
   }
   ```

**Reporter System Prompt** (key sections):

- Personality: "Empathetic but concise — keep responses under 50 words"
- Health signal detection: Explicit examples of what SHOULD and SHOULD NOT trigger investigation
- Data collection order: What → Where → When → Who (but flexible)
- JSON response format: `response`, `detected_language`, `health_signal_detected`, `extracted_data`, `transition_to`, `reasoning`
- Tone examples in both English and Arabic (good vs bad)
- Rules: Never ask for PII, never provide medical advice, never promise response times

### Surveillance Agent

**File: `cbi/agents/surveillance.py`**

**LLM Config**: Claude Sonnet, 2000 tokens, temperature 0.1, 60s timeout

The surveillance agent is the epidemiological classifier. It performs five steps:

**Step 1 — LLM Classification**:
```python
response = await client.messages.create(
    model=config.model,
    system=format_surveillance_prompt(extracted_data),
    messages=[{"role": "user", "content": f"Classify this health report:\n{report_summary}"}],
)
```

**Step 2 — Parse & Validate**: Reuses `parse_json_response` from reporter. Falls back to `{urgency: "medium", alert_type: "single_case"}` on failure.

**Step 3 — Database Operations** (four sub-steps in separate transactions):

3a. **Query related cases**: Uses `find_related_cases()` which combines PostGIS spatial proximity + symptom array overlap + Jaccard similarity scoring.

3b. **Check MoH thresholds**:
```python
THRESHOLDS = {
    "cholera":    {"alert_cases": 1,  "outbreak_cases": 3,  "window_days": 7,  "any_death_is_critical": True},
    "dengue":     {"alert_cases": 5,  "outbreak_cases": 20, "window_days": 7,  "any_death_is_critical": True},
    "malaria":    {"alert_cases": 10, "outbreak_cases": 50, "window_days": 7,  "any_death_is_critical": False},
    "measles":    {"alert_cases": 1,  "outbreak_cases": 5,  "window_days": 14, "any_death_is_critical": True},
    "meningitis": {"alert_cases": 1,  "outbreak_cases": 3,  "window_days": 7,  "any_death_is_critical": True},
    "unknown":    {"alert_cases": 5,  "outbreak_cases": 10, "window_days": 7,  "any_death_is_critical": True},
}
```

3c. **Calculate final urgency** — takes the **higher** of rule-based and LLM-suggested urgency:
```python
def calculate_urgency(classification_data, total_area_cases, deaths_reported):
    if deaths_reported > 0: rule_urgency = "critical"
    elif disease in ("cholera", "meningitis"): rule_urgency = "critical"
    elif total_area_cases >= 10: rule_urgency = "critical"
    elif total_area_cases >= 3: rule_urgency = "high"
    else: rule_urgency = "medium"

    llm_urgency = classification_data.get("urgency", "medium")
    return max(rule_urgency, llm_urgency)  # by _URGENCY_ORDER
```

3d. **Create report** in PostgreSQL (separate transaction from case linking).

3e. **Link related cases** in another separate transaction:
```python
for related in related_cases:
    link_type = _determine_link_type(symptoms, location_text, related)
    await link_reports(session, report_id, related["id"], link_type, confidence)
```

Link type determination priority: geographic > symptom > temporal.

**Graceful degradation**: If the Surveillance Agent's LLM call fails, it returns a default medium-urgency classification with `"Manual review required"` in recommended actions. The pipeline continues and a notification is still created. This is intentionally **not** an error state — the report should still reach health officers.

### Analyst Agent

**File: `cbi/agents/analyst.py`**

**LLM Config**: Claude Sonnet, 4000 tokens, temperature 0.1, 120s timeout

The Analyst Agent has two modes of operation:

#### Mode 1: LangGraph Node (Situation Summaries)

When triggered by the graph (urgency = critical/high), generates a situation summary:
```python
async def analyst_node(state: ConversationState) -> ConversationState:
    # Calls Claude with classification data + area statistics
    # Generates summary in English and Arabic
    # Returns updated state with summary in classification
```

#### Mode 2: API Endpoint (Natural Language Queries)

Health officers ask questions like "How many cholera cases this week?" The analyst processes through a 4-step pipeline:

1. **`parse_query_intent()`** — LLM extracts query_type, parameters (disease, location, time_range, urgency_filter)
2. **`generate_sql()`** — LLM generates PostgreSQL SELECT with schema context, then validates
3. **`execute_query()`** — Runs with `asyncio.wait_for()` timeout (30s) and creates audit log
4. **`format_query_response()`** — Determines visualization type and formats results

#### SQL Security Model

```python
ALLOWED_TABLES = frozenset({"reports", "notifications", "report_links"})

FORBIDDEN_SQL_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC", "INTO",
    "SET", "MERGE", "CALL", "REPLACE",
})

def validate_sql_query(sql):
    # 1. Must start with SELECT or WITH
    # 2. No forbidden keywords (word-boundary regex)
    # 3. Max 1 semicolon (at end only)
    # 4. No SQL injection patterns (comments, chained queries, UNION ALL SELECT)
    # 5. All tables must be in ALLOWED_TABLES (CTE names excluded)
```

This is a defense-in-depth approach: the LLM is instructed to generate safe queries, but the validation layer enforces it independently.

### Agent-Specific LLM Configurations

**File: `cbi/config/llm_config.py`**

```python
SONNET_MODEL = "claude-sonnet-4-5-20250929"

REPORTER_CONFIG = LLMConfig(model=SONNET_MODEL, max_tokens=500,  temperature=0.3, timeout=30.0)
SURVEILLANCE_CONFIG = LLMConfig(model=SONNET_MODEL, max_tokens=2000, temperature=0.1, timeout=60.0)
ANALYST_CONFIG = LLMConfig(model=SONNET_MODEL, max_tokens=4000, temperature=0.1, timeout=120.0)
```

**Why different temperatures**:
- Reporter (0.3): Needs some variation for natural conversation but must be consistent in JSON output
- Surveillance (0.1): Classification should be deterministic — same symptoms should produce same urgency
- Analyst (0.1): SQL generation must be precise — no creative queries

**Why different token limits**:
- Reporter (500): Responses must be under 50 words per design constraint
- Surveillance (2000): Classification reasoning + recommended actions + follow-up questions
- Analyst (4000): SQL queries + explanations + formatted results

---

## 6. Database Design

### Schema Overview

**File: `cbi/db/models.py`**

7 tables using SQLAlchemy 2.0 `mapped_column` syntax:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   reporters  │     │   officers   │     │ audit_logs   │
│              │     │              │     │              │
│ id (UUID)    │◄──┐ │ id (UUID)    │◄──┐ │ entity_type  │
│ phone_hash   │   │ │ email        │   │ │ entity_id    │
│ phone_encrypt│   │ │ password_hash│   │ │ action       │
│ language     │   │ │ name         │   │ │ changes JSONB│
│ total_reports│   │ │ region       │   │ └──────────────┘
└──────────────┘   │ │ role         │   │
                   │ │ is_active    │   │
                   │ └──────────────┘   │
                   │                    │
┌──────────────┐   │                    │   ┌──────────────┐
│   reports    │   │                    │   │notifications │
│              │   │                    │   │              │
│ id (UUID)    │───┤                    ├──►│ report_id    │
│ reporter_id  │───┘                    │   │ officer_id   │
│ officer_id   │────────────────────────┘   │ urgency      │
│ symptoms[]   │                            │ title        │
│ disease      │◄───────────────────────────│ body         │
│ location_text│                            │ read_at      │
│ location_pt  │ (Geography POINT)          └──────────────┘
│ urgency      │
│ alert_type   │    ┌──────────────┐
│ cases_count  │    │ report_links │
│ deaths_count │    │              │
│ raw_convo    │◄───│ report_id_1  │
│ status       │◄───│ report_id_2  │
└──────────────┘    │ link_type    │
                    │ confidence   │
┌──────────────┐    └──────────────┘
│conversation_ │
│   states     │
│              │
│ conversation_│
│   id (PK)   │
│ reporter_id  │
│ state JSONB  │
│ mode         │
│ turn_count   │
└──────────────┘
```

### Key Design Decisions

#### Phone Number Privacy (Two-Layer Protection)

```python
class Reporter(Base):
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 for lookups
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary)       # AES-256 for retrieval
```

- **Hash** (SHA-256 with salt): Used for finding existing reporters. One-way, cannot recover phone number. Indexed for O(1) lookups.
- **Encrypted** (AES-256): Used when a health officer needs to contact the reporter. Reversible with the encryption key.

#### PostGIS Geography Column

```python
location_point = mapped_column(Geography(geometry_type="POINT", srid=4326))
```

Uses `Geography` type (not `Geometry`) for accurate distance calculations on the Earth's surface. SRID 4326 is WGS84 (GPS coordinates). Indexed with GiST for spatial queries.

#### JSONB Columns for Flexible Data

```python
raw_conversation: Mapped[dict] = mapped_column(JSONB, default=list)   # Full conversation history
extracted_entities: Mapped[dict] = mapped_column(JSONB, default=dict)  # NER results
investigation_notes: Mapped[list] = mapped_column(JSONB, default=list) # Officer annotations
```

JSONB is used for data that:
- Varies in structure between reports
- Needs to be queried but not joined on
- Would require many nullable columns if normalized

#### Report Link Constraints

```python
class ReportLink(Base):
    __table_args__ = (
        CheckConstraint("report_id_1 != report_id_2", name="different_reports"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="valid_link_confidence"),
        UniqueConstraint("report_id_1", "report_id_2", "link_type", name="unique_link"),
    )
```

Database-level constraints prevent:
- Self-links
- Invalid confidence scores
- Duplicate links of the same type between the same reports

### Key Indexes

```python
# GiST index on geography column for spatial queries
Index("idx_reports_location", "location_point", postgresql_using="gist")

# Partial index for the most common query pattern (open + urgent reports)
Index("idx_reports_open_urgent", "urgency", "created_at",
      postgresql_where="status = 'open'")

# Partial index for unread notifications
Index("idx_notifications_unread", "officer_id", "sent_at",
      postgresql_where="read_at IS NULL")
```

### Geospatial Queries

**File: `cbi/db/queries.py`**

**Finding related cases within radius**:
```python
async def get_reports_near_location(session, latitude, longitude, radius_km=10.0, days=7):
    point = f"SRID=4326;POINT({longitude} {latitude})"
    result = await session.execute(
        select(Report).where(and_(
            Report.location_point.isnot(None),
            Report.created_at >= since,
            func.ST_DWithin(
                Report.location_point,
                func.ST_GeogFromText(point),
                radius_km * 1000,  # km → meters
            ),
        ))
    )
```

**`find_related_cases`** combines three signals:
1. **Geographic proximity**: `ST_DWithin` with configurable radius
2. **Symptom overlap**: PostgreSQL array `&&` (overlap) operator
3. **Jaccard similarity**: `len(intersection) / len(union)` for symptom arrays

### Geocoding (Offline Dictionary)

```python
_SUDAN_LOCATIONS = {
    "khartoum": (15.5007, 32.5599),
    "الخرطوم": (15.5007, 32.5599),
    "omdurman": (15.6445, 32.4777),
    "أم درمان": (15.6445, 32.4777),
    # ~25 locations with Arabic/English variants
}
```

This is an offline geocoding dictionary, not an API call. It maps known Sudan locations (in both Arabic and English) to coordinates. The `backfill_report_locations()` function runs at startup to geocode reports that have `location_text` but no `location_point`.

### Session Management

**File: `cbi/db/session.py`**

```python
_async_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevents lazy-loading issues in async context
    autocommit=False,
    autoflush=False,
)

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

`expire_on_commit=False` is critical for async usage — without it, accessing relationship attributes after `commit()` would trigger lazy loads that fail in an async context.

---

## 7. Messaging Gateway Abstraction

### Architecture

```
                ┌─────────────────────┐
                │  MessagingGateway   │ (Abstract Base Class)
                │                     │
                │  send_message()     │
                │  send_template()    │
                │  parse_webhook()    │
                │  close()            │
                └──────────┬──────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
  ┌───────────┴──────────┐  ┌──────────┴───────────┐
  │  TelegramGateway     │  │  WhatsAppGateway     │
  │                      │  │                      │
  │  httpx.AsyncClient   │  │  httpx.AsyncClient   │
  │  HTML parse mode     │  │  Meta Graph API      │
  │  Telegram Bot API    │  │  Template messages    │
  └──────────────────────┘  └──────────────────────┘
```

### Platform-Agnostic Data Classes

**File: `cbi/services/messaging/base.py`**

```python
@dataclass(frozen=True)
class IncomingMessage:
    platform: str       # "telegram" | "whatsapp"
    message_id: str
    chat_id: str
    from_id: str
    text: str | None
    timestamp: datetime
    reply_to_id: str | None = None

@dataclass
class OutgoingMessage:
    chat_id: str
    text: str
    reply_to_id: str | None = None
```

`IncomingMessage` is frozen (immutable) since it represents received data. `OutgoingMessage` is mutable since the gateway may need to modify it (e.g., adding parse mode).

### Factory Pattern with Singleton Caching

**File: `cbi/services/messaging/factory.py`**

```python
_gateway_cache: dict[str, MessagingGateway] = {}

def get_gateway(platform: str) -> MessagingGateway:
    if platform in _gateway_cache:
        return _gateway_cache[platform]
    gateway = _create_gateway(platform)
    _gateway_cache[platform] = gateway
    return gateway
```

Singletons per platform ensure HTTP client reuse (connection pooling via httpx).

### Platform Detection from Webhook Data

```python
def get_gateway_for_message(data: dict) -> tuple[MessagingGateway, str] | None:
    if "update_id" in data or "message" in data:       # Telegram
        return get_gateway("telegram"), "telegram"
    if data.get("object") == "whatsapp_business_account":  # WhatsApp
        return get_gateway("whatsapp"), "whatsapp"
    return None
```

### Telegram Implementation Details

**File: `cbi/services/messaging/telegram.py`**

- Uses **httpx.AsyncClient** with 30-second timeout
- Messages sent with **HTML parse mode**
- **Error hierarchy**: `MessagingAuthenticationError` (401), `MessagingRateLimitError` (429), `MessagingSendError` (other)
- Default templates for welcome, confirmation, and error messages in English and Arabic
- `parse_webhook()` handles `message` and `edited_message` update types, skips non-text content (photos, stickers, etc.) for MVP

---

## 8. State Management (Redis)

### Service Architecture

**File: `cbi/services/state.py`**

```python
class StateService:
    """
    Key patterns:
    - cbi:conversation:{conversation_id} → Full ConversationState JSON
    - cbi:session:{platform}:{phone_hash} → conversation_id
    """

    state_ttl = 24 * 60 * 60   # 24 hours
    session_ttl = 60 * 60       # 1 hour
```

### Session Resolution Flow

```
User sends message
    │
    ▼
Phone number → SHA-256 hash (truncated to 16 chars)
    │
    ▼
Redis GET cbi:session:telegram:{phone_hash}
    │
    ├── Found conversation_id → Load state
    │       │
    │       ├── Mode = "complete" or "error" → Start new conversation
    │       │
    │       └── Active conversation → Resume, extend session TTL
    │
    └── Not found → Create new conversation with initial state
```

### State Lifecycle

1. **Created**: `create_initial_state()` with mode=`listening`, empty extracted_data and classification
2. **Updated**: After each turn, `save_state()` serializes to JSON and sets with TTL
3. **Session maintained**: Session key TTL extended on every access
4. **Expired**: State TTL (24h) or session TTL (1h) → Redis auto-deletes
5. **Completed/Error**: Next message from same user creates a new conversation

### Conversation ID Format

```python
def _generate_conversation_id(self):
    return f"conv_{uuid.uuid4().hex[:16]}"
    # e.g., "conv_a3f8b2c1d4e5f6a7"
```

### Phone Hashing for Session Keys

```python
def _phone_hash(self, phone: str) -> str:
    salt = self._settings.phone_hash_salt.get_secret_value()
    data = f"{salt}{phone}".encode()
    full_hash = hashlib.sha256(data).hexdigest()
    return full_hash[:16]  # Truncated for Redis key efficiency
```

Truncated to 16 characters because:
- Redis keys should be short for memory efficiency
- 16 hex chars = 64 bits = collision probability negligible for expected user count
- The salt prevents rainbow table attacks

---

## 9. Real-time System

### Architecture

```
                    LangGraph Pipeline
                           │
                           ▼
                send_notification_node()
                    │            │
                    ▼            ▼
              PostgreSQL    Redis Pub/Sub
              (persistent)  (transient)
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              notifications: notifications: reports:
              {officer_id}  broadcast    updates
                    │           │           │
                    └───────────┼───────────┘
                                │
                                ▼
                        WebSocket Server
                        (FastAPI route)
                                │
                                ▼
                        Dashboard Clients
                        (Socket.io)
```

### Channel Structure

**File: `cbi/services/realtime.py`**

```python
CHANNEL_NOTIFICATION_PREFIX = "notifications:"  # Per-officer: notifications:{officer_id}
CHANNEL_BROADCAST = "notifications:broadcast"    # All officers
CHANNEL_REPORT_UPDATES = "reports:updates"       # Report create/update events
```

### Publish Flow

When `send_notification_node` runs:
1. Creates `Notification` records in PostgreSQL for each active officer
2. Publishes to Redis `notifications:broadcast` channel:
   ```python
   await realtime.broadcast({
       "type": "new_alert",
       "id": str(notification_ids[0]),
       "title": notification_title,
       "body": notification_body,
       "urgency": urgency,
       "report_id": str(state.get("report_id")),
       "timestamp": datetime.utcnow().isoformat(),
   })
   ```

### Frontend Subscription (Socket.io)

**File: `dashboard/src/hooks/useRealtime.ts`**

```typescript
const socket = io(wsUrl, { autoConnect: false });
socket.on("new_alert", (data) => {
    addNotification(data);
    playAlertSound(data.urgency);
    toast({ title: data.title, description: data.body });
});
```

The dashboard plays different alert sounds based on urgency level and shows toast notifications in real-time.

---

## 10. Frontend Dashboard

### Architecture

**Framework**: Next.js 14 with App Router

```
dashboard/src/
├── app/
│   ├── layout.tsx           # Root layout with providers
│   ├── providers.tsx        # React Query + Theme providers
│   ├── (auth)/
│   │   └── login/page.tsx   # Login form
│   └── (dashboard)/
│       ├── page.tsx         # Overview: stats + charts + alerts
│       ├── reports/
│       │   ├── page.tsx     # Report list with filters
│       │   └── [id]/page.tsx # Report detail + conversation
│       ├── analytics/page.tsx # Disease trends + analytics
│       └── map/page.tsx     # Leaflet incident map
├── components/
│   ├── ui/                  # shadcn/ui primitives
│   ├── layout/              # Sidebar, Header, MobileNav
│   ├── dashboard/           # StatsCard, RecentAlerts, CasesTrend
│   ├── reports/             # ReportTable, ReportFilters, ConversationView
│   ├── map/                 # IncidentMap, MapMarker
│   ├── charts/              # DiseaseDistribution (Recharts)
│   └── notifications/       # NotificationBell, NotificationPanel
├── hooks/
│   ├── useAuth.ts           # Login/logout/me (React Query)
│   ├── useReports.ts        # Report CRUD (React Query)
│   ├── useAnalytics.ts      # Analytics data (React Query)
│   └── useRealtime.ts       # WebSocket connection
├── lib/
│   └── api.ts               # APIClient with auth header injection
├── stores/
│   ├── authStore.ts         # Zustand + persist (tokens)
│   └── notificationStore.ts # Zustand (notification state)
└── types/
    └── index.ts             # Report, Officer, Notification types
```

### State Management Strategy

| Concern | Tool | Why |
|---------|------|-----|
| Server state (reports, notifications) | React Query | Caching, background refetching, pagination |
| Auth tokens | Zustand + persist | Survives page refresh via localStorage |
| Notification count/preferences | Zustand | Lightweight, no persistence needed |
| Real-time updates | Socket.io + Zustand | WebSocket events update Zustand store |

### API Client

**File: `dashboard/src/lib/api.ts`**

```typescript
class APIClient {
    private baseUrl: string;

    async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
        const token = useAuthStore.getState().accessToken;
        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...(token && { Authorization: `Bearer ${token}` }),
                ...options?.headers,
            },
        });
        if (response.status === 401) {
            useAuthStore.getState().logout();
        }
        return response.json();
    }
}
```

Automatic token injection and 401 redirect to login.

### Key Dashboard Pages

#### Overview (`(dashboard)/page.tsx`)
- **StatsCards**: Total reports, open cases, critical alerts, affected regions (last 7 days)
- **CasesTrend**: Line chart of daily case counts (Recharts)
- **DiseaseDistribution**: Pie/bar chart by disease type
- **RecentAlerts**: Last 10 notifications with urgency badges

#### Reports (`(dashboard)/reports/page.tsx`)
- **ReportTable**: Paginated table with sortable columns
- **ReportFilters**: Filter by status, urgency, disease, date range, location
- **Export**: Download filtered reports as CSV/JSON

#### Report Detail (`(dashboard)/reports/[id]/page.tsx`)
- Report metadata (disease, urgency, location, case count)
- **ConversationView**: Full chat history between reporter and AI agent
- Status update controls (open → investigating → resolved/false_alarm)
- Investigation notes (officer annotations)
- Linked cases list

#### Map (`(dashboard)/map/page.tsx`)
- **React Leaflet** with OpenStreetMap tiles
- Report markers colored by urgency (critical=red, high=orange, medium=yellow, low=green)
- Marker popups with disease, case count, and link to report detail
- Filter by disease type and date range

#### Analytics (`(dashboard)/analytics/page.tsx`)
- Disease trend line charts (7/30/90 day views)
- Geographic distribution bar charts
- Urgency breakdown
- Natural language query interface (powered by Analyst Agent)

---

## 11. Security Architecture

### Authentication Flow

**File: `cbi/services/auth.py`**

```
Officer Login
    │
    ▼
POST /api/auth/login {email, password}
    │
    ├── bcrypt.checkpw(password, stored_hash)
    │
    ├── Success → Return {access_token (24h), refresh_token (7d)}
    │
    └── Failure → 401 Unauthorized
```

```python
def create_access_token(officer_id, role="officer"):
    payload = {
        "sub": str(officer_id),
        "role": role,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
```

**Token refresh** and **blacklisting**:
```python
async def blacklist_token(redis_client, token, expires_in):
    await redis_client.setex(f"token:blacklist:{token}", expires_in, "1")
```

Blacklist entries auto-expire when the token would have expired, preventing stale Redis data.

### PII Protection (Multiple Layers)

1. **Phone Number Storage**: SHA-256 hash for lookups + AES-256 encryption for retrieval
2. **Structured Logging PII Filter**:
   ```python
   PII_PATTERNS = [
       (re.compile(r"\+?[0-9]{10,15}"), "[PHONE_REDACTED]"),
       (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL_REDACTED]"),
       (re.compile(r"\b\d{11}\b"), "[ID_REDACTED]"),  # Sudan national ID
   ]
   ```
3. **Reporter Agent Prompt**: "NEVER ask for personal identification information (name, ID, exact address)"
4. **Phone hash in state service**: Uses truncated SHA-256 for Redis session keys

### SQL Injection Prevention (Analyst Agent)

Defense-in-depth with three layers:

1. **LLM Prompt**: "Only use SELECT statements — no modifications"
2. **Code Validation** (`validate_sql_query()`):
   - Must start with SELECT or WITH
   - Forbidden keywords checked with word-boundary regex
   - Max 1 semicolon (end only)
   - Injection patterns detected (`--`, `/*`, `; SELECT`, `UNION ALL SELECT`)
   - Table whitelist enforcement
3. **Audit Logging**: Every query execution is logged with officer ID, SQL preview, and result count

### Webhook Security

- Telegram webhook secret token validation (configurable)
- WhatsApp webhook signature validation using HMAC-SHA256 with app secret
- Both platforms' webhook handlers validate before processing

### CORS

```python
allow_origins=["http://localhost:3000"] if settings.is_development else []
```

Production blocks all cross-origin requests (dashboard should be served from same domain or configured with specific origins).

### Rate Limiting

Configured in settings:
```python
rate_limit_requests: int = 100     # per window
rate_limit_window_seconds: int = 60
login_rate_limit: int = 5          # login attempts
login_rate_limit_window: int = 60
```

### Docker Security

```dockerfile
# Non-root user for production
RUN groupadd --gid 1000 cbi && useradd --uid 1000 --gid cbi cbi
USER cbi
```

---

## 12. Testing Strategy

### Test Structure

```
tests/
├── unit/                    # Pure function tests (no DB/Redis/LLM)
│   ├── test_crypto.py       # Phone hashing, encryption
│   ├── test_language.py     # Arabic/English detection
│   ├── test_messaging.py    # Gateway parsing, message creation
│   ├── test_prompts.py      # Prompt formatting, response validation
│   └── test_state.py        # State transitions, MVS fields, completeness
├── agents/                  # Agent tests with mocked LLM
│   ├── test_reporter_intent.py       # Health signal detection (golden dataset)
│   ├── test_reporter_extraction.py   # MVS data extraction
│   ├── test_surveillance_classification.py # Disease classification
│   └── test_full_conversation.py     # Multi-turn conversation flows
├── integration/             # Real DB tests (PostgreSQL + PostGIS)
│   ├── test_api_auth.py     # Login, refresh, protected routes
│   ├── test_api_reports.py  # Report CRUD, filtering, status updates
│   ├── test_database_queries.py      # PostGIS queries, report stats
│   ├── test_report_flow.py  # End-to-end report creation + classification
│   └── test_webhook_flow.py # Webhook → queue → processing
├── test_analyst_agent.py    # Analyst SQL generation + validation
├── test_notification_flow.py # Notification creation + delivery
├── test_realtime_websocket.py # WebSocket pub/sub
└── test_surveillance_flow.py # Surveillance agent flow
```

### Test Counts

| Category | Count | Focus |
|----------|-------|-------|
| Unit tests | 217 | State transitions, crypto, language detection, prompt validation |
| Agent tests | 155 | LLM interaction with mocked Claude, intent detection golden dataset |
| Integration tests | 56 | Real PostgreSQL/PostGIS, API endpoints, full report flows |
| **Total passing** | **428** | + 8 pre-existing fixture errors in notification/websocket tests |

### Testing Approach

#### Unit Tests (no external dependencies)

Test pure functions like state transitions, data completeness scoring, language detection:

```python
def test_calculate_completeness_all_fields():
    extracted = ExtractedData(
        symptoms=["fever", "cough"],
        location_text="Khartoum",
        onset_text="3 days ago",
        cases_count=5,
        reporter_relationship="family",
        affected_description="children",
    )
    assert calculate_data_completeness(extracted) == 1.0

def test_arabic_detection():
    assert detect_language("أنا مريض") == "ar"
    assert detect_language("I am sick") == "en"
```

#### Agent Tests (mocked LLM)

Use `unittest.mock.patch` to mock `anthropic.AsyncAnthropic.messages.create`:

```python
@patch("cbi.agents.reporter.get_anthropic_client")
async def test_health_signal_detection(mock_client):
    mock_client.return_value.messages.create.return_value = MockResponse(
        json.dumps({
            "response": "I'm sorry to hear that...",
            "health_signal_detected": True,
            "transition_to": "investigating",
            "extracted_data": {"symptoms": ["vomiting", "diarrhea"]},
        })
    )
    state = create_initial_state("conv_1", "+249123456789")
    state = add_message_to_state(state, "user", "People are vomiting in my area")
    result = await reporter_node(state)
    assert result["current_mode"] == "investigating"
```

**Golden dataset** for intent detection: Tests that SHOULD trigger investigation (current symptoms, deaths, outbreaks) and SHOULD NOT (educational questions, past events, news).

#### Integration Tests (real database)

Uses `pytest-asyncio` with session-scoped async fixtures:

```python
# conftest.py sets env vars BEFORE any cbi.* import
os.environ["DATABASE_URL"] = "postgresql+asyncpg://..."
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

@pytest_asyncio.fixture(loop_scope="session")
async def db_engine():
    engine = create_async_engine(test_db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
```

Tests real PostGIS spatial queries, report creation, case linking, and API endpoint responses.

### Key Testing Gotchas (from experience)

1. `pytest-asyncio` 1.x auto mode overrides explicit `loop_scope="session"` — must set `asyncio_default_test_loop_scope = "session"` in `pyproject.toml`
2. `.test` TLD is rejected by `email-validator` (RFC 2606 reserved) — use `.example.com` for test emails
3. Lazy-loaded relationships fail in async context after `session.commit()` — set `expire_on_commit=False`
4. Integration `conftest.py` must set env vars BEFORE any `cbi.*` import (due to `@lru_cache` on `get_settings()`)
5. `geoalchemy2.func` is not a thing in v0.18.1 — use `sqlalchemy.func` for `ST_DWithin`

---

## 13. DevOps & Deployment

### Docker Compose (Local Development)

**File: `docker-compose.yml`**

6 services:

| Service | Image/Build | Port | Purpose |
|---------|------------|------|---------|
| `api` | Custom Dockerfile (dev target) | 8000 | FastAPI backend with hot reload |
| `worker` | Same Dockerfile, different CMD | — | Background message processor |
| `dashboard` | dashboard/Dockerfile (dev target) | 3000 | Next.js with hot reload |
| `db` | `kartoza/postgis:15-3.3` | 5432 | PostgreSQL 15 + PostGIS 3.3 |
| `redis` | `redis:7-alpine` | 6379 | Cache + queue + pub/sub |
| `ngrok` | `ngrok/ngrok:latest` | 4040 | Telegram webhook tunnel |

**Service dependencies**:
```
dashboard → api → db + redis
worker → api → db + redis
ngrok → api
```

**Redis configuration**:
```yaml
command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```
AOF persistence enabled, 256MB memory limit with LRU eviction.

### Multi-Stage Dockerfile

**File: `Dockerfile`**

```
Stage 1: builder (python:3.11-slim)
    ├── Install build-essential, libpq-dev
    ├── Create virtual environment
    └── pip install dependencies

Stage 2: runtime (python:3.11-slim)
    ├── Install libpq5, curl (runtime only)
    ├── Create non-root user (cbi:1000)
    ├── Copy venv from builder
    ├── Copy application code
    └── CMD: uvicorn cbi.api.main:app

Stage 3: development (extends runtime)
    ├── pip install ".[dev]" (test + lint dependencies)
    └── CMD: uvicorn ... --reload
```

### Health Checks

**API**: `curl -f http://localhost:8000/health` — checks both PostgreSQL and Redis connectivity

**Worker**: Separate aiohttp server on port 8081:
- `/health` — liveness (always 200 if worker is running)
- `/ready` — readiness (checks Redis + queue connectivity)
- `/metrics` — worker stats (messages processed, success rate, avg time)

**Database**: `pg_isready -U cbi -d cbi`

**Redis**: `redis-cli ping`

### Database Extensions

**File: `scripts/init-db/01-init-extensions.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

- `postgis`: Spatial queries (ST_DWithin, Geography types)
- `uuid-ossp`: UUID generation in database (uuid_generate_v4)
- `pg_trgm`: Trigram-based text similarity (for location fuzzy matching)

### AWS Architecture (Planned)

```
┌──────────────────────────────────────────────────┐
│                     VPC                           │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ ECS Fargate │  │ ECS Fargate │  │ ECS      │ │
│  │   (API)     │  │  (Worker)   │  │(Dashboard)│ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┘ │
│         │                │                        │
│  ┌──────┴────────────────┴──────┐                │
│  │        Internal Network       │                │
│  └──────┬────────────────┬──────┘                │
│         │                │                        │
│  ┌──────┴──────┐  ┌─────┴───────┐               │
│  │   RDS       │  │ ElastiCache │               │
│  │ (PostGIS)   │  │  (Redis)    │               │
│  └─────────────┘  └─────────────┘               │
└──────────────────────────────────────────────────┘
```

Serverless containers (no EC2 management), managed database, managed Redis.

---

## 14. Key Design Decisions & Tradeoffs

### 1. LLM Intent Detection over Keyword Matching

**Decision**: Use Claude's language understanding to detect health signals, not regex/keyword matching.

**Why**: Community members describe symptoms in natural language ("people are vomiting and have watery diarrhea") not medical terms ("suspected cholera"). Keyword matching would miss contextual cues and produce many false positives/negatives.

**Tradeoff**: LLM calls add latency (~2-3 seconds per turn) and cost (~$0.01 per conversation). Keyword matching would be instant and free. But accuracy matters more than speed for health surveillance — a missed outbreak is far worse than a 3-second delay.

### 2. Flexible Data Collection over Rigid Forms

**Decision**: Accept partial, vague information. "A few days ago" is acceptable for onset_text.

**Why**: Reporters are stressed community members, not trained data entry operators. Blocking on "please provide an exact date" would cause drop-off and lost reports.

**Tradeoff**: Data completeness varies (some reports have 30% completeness). But the weighted scoring system ensures the most important fields (symptoms, location) are prioritized, and even partial reports contribute to geographic pattern detection.

### 3. Dual Urgency Calculation (Rules + LLM)

**Decision**: `calculate_urgency()` takes the **higher** of rule-based and LLM-suggested urgency.

**Why**: Rule-based logic catches known patterns (any cholera = critical, deaths = critical). LLM catches nuanced patterns (vulnerable populations, rapid spread). Taking the max ensures we never under-triage.

**Tradeoff**: This biases toward over-triage. Some reports may be flagged as higher urgency than warranted. But in health surveillance, false positives are far less dangerous than false negatives.

### 4. Redis for Triple-Duty (State + Queue + Pub/Sub)

**Decision**: Use Redis for conversation state, message queuing (Streams), and real-time events (pub/sub).

**Why**: One dependency instead of three (Redis + RabbitMQ + separate pub/sub). Redis Streams provide reliable queuing with consumer groups and message acknowledgment. The system handles ~2000 messages/day — well within Redis's capabilities.

**Tradeoff**: Redis is a single point of failure for all three concerns. If Redis goes down, we lose conversation state, message queue, AND real-time updates. In production, this is mitigated by ElastiCache with Multi-AZ failover.

### 5. Separate Transactions for Report + Case Linking

**Decision**: Report creation and case linking happen in separate database transactions.

```python
# 3d. Create report (own transaction)
async with get_session() as session:
    report_id = await create_report_from_state(session, state)

# 3e. Link related cases (separate transaction)
async with get_session() as session:
    for related in related_cases:
        await link_reports(session, report_id, related["id"], ...)
```

**Why**: If case linking fails (e.g., duplicate link constraint violation), the report should still be saved. Reports are critical data; links are supplementary intelligence.

**Tradeoff**: Brief window where report exists without links. But links are auto-detected on next report anyway, so missing links are self-healing.

### 6. Offline Geocoding Dictionary

**Decision**: Use a hardcoded dictionary of ~25 Sudan locations instead of a geocoding API.

**Why**: External geocoding APIs (Google Maps, Nominatim) have latency, rate limits, and costs. Sudan's location names are often in Arabic, which many geocoding services handle poorly. The dictionary covers the most commonly reported locations.

**Tradeoff**: Only ~25 known locations can be geocoded. Reports from unlisted locations get no coordinates and can't participate in spatial queries. The `backfill_report_locations()` function at startup attempts to geocode existing reports as the dictionary grows.

### 7. TypedDict over Pydantic for LangGraph State

**Decision**: `ConversationState` is a `TypedDict`, not a Pydantic model.

**Why**: LangGraph requires `TypedDict` for state schemas. The `total=False` parameter allows partial state updates, which is essential for the graph pattern where each node only updates the fields it's responsible for.

**Tradeoff**: No runtime validation on state updates (unlike Pydantic). But the nested data models (`ExtractedData`, `Classification`) are Pydantic models with validation, so the most important data structures are still validated.

### 8. HTML Parse Mode for Telegram

**Decision**: Send messages with `parse_mode: "HTML"` instead of Markdown.

**Why**: Markdown v2 in Telegram requires escaping many common characters (`.`, `-`, `!`). HTML is more predictable and doesn't clash with Arabic text that may contain these characters.

---

## 15. Scalability Considerations

### Current Capacity

| Component | Current Limit | Bottleneck |
|-----------|--------------|------------|
| API | ~100 concurrent requests | uvicorn worker count (1 in dev, 4 in prod) |
| Worker | 1 message at a time (sequential) | LLM API call latency (~3s per message) |
| Database | Pool of 5+10 connections | PostGIS spatial queries on large datasets |
| Redis | 256MB memory | Conversation state (~2KB per conversation) |
| LLM API | Rate limited by Anthropic | ~50 requests/minute on standard tier |

### Scaling Strategies

#### Horizontal Worker Scaling

Redis Streams consumer groups enable multiple workers to process messages in parallel without duplication:

```python
# Worker 1
async for entry_id, message in consume_messages("worker-1"):
    ...
# Worker 2 (separate container)
async for entry_id, message in consume_messages("worker-2"):
    ...
```

Each worker claims different messages from the same stream. No coordination needed beyond Redis.

#### Database Scaling

- **Read replicas**: Analytics queries (Analyst Agent) can be directed to read replicas
- **Table partitioning**: Reports table can be partitioned by `created_at` (monthly) for large datasets
- **Spatial index**: GiST index on `location_point` handles spatial queries efficiently

#### Redis Scaling

- **ElastiCache cluster mode**: Shard conversation state across multiple Redis nodes
- **Separate Redis instances**: One for state (persistent), one for pub/sub (ephemeral)
- Redis Stream maxlen of 10,000 messages prevents unbounded growth

#### LLM API Scaling

- **Request batching**: Queue multiple classification requests and process in batch
- **Caching**: Cache classification results for identical symptom patterns
- **Model fallback**: If Sonnet is rate-limited, fall back to Haiku for Reporter (still good Arabic)

### Estimated Capacity at Scale

With 4 workers, managed PostgreSQL, and ElastiCache:
- **~10,000 messages/day** (5x the design target of 2,000)
- **~500 concurrent conversations**
- **<10 second** end-to-end latency for complete report flow

---

## 16. Challenges & Solutions

### Challenge 1: Arabic Language Understanding

**Problem**: Arabic is morphologically complex (right-to-left, connected letters, dialectal variation). Sudanese Arabic differs significantly from Modern Standard Arabic (MSA).

**Solution**: Claude Sonnet handles Arabic natively with excellent dialectal understanding. Language detection uses Unicode character analysis (not NLP libraries) with a 30% threshold — mixed Arabic/English messages are classified as Arabic since the health signal is likely in Arabic.

**Why this works**: The Reporter Agent prompt includes Arabic response examples and explicitly supports bilingual conversations. The system doesn't require language consistency within a conversation.

### Challenge 2: Structured Data from Unstructured Conversation

**Problem**: Extracting specific fields (symptoms, location, onset date, case count) from natural conversation where information may be scattered across multiple messages.

**Solution**: The `extracted_data` dict accumulates across turns. Each LLM response includes an `extracted_data` field that is **merged** (not replaced):
```python
def extract_data_from_response(parsed, current_data):
    for key, value in extracted.items():
        if isinstance(value, list) and len(value) > 0:
            combined = list(dict.fromkeys(existing + value))  # Deduplicated merge
            updates[key] = combined
```

Symptoms mentioned in turn 2 are added to symptoms from turn 1, not overwritten.

### Challenge 3: LLM Response Reliability

**Problem**: Claude sometimes returns non-JSON responses, malformed JSON, or responses missing required fields.

**Solution**: Three-level JSON parsing with graceful fallback:
1. Extract from markdown code blocks
2. Parse entire response as JSON
3. Find any `{...}` in the response
4. Fall back to raw text as user response

Plus response validation (`validate_reporter_response`) that logs warnings but doesn't crash.

### Challenge 4: Async SQLAlchemy + PostGIS

**Problem**: Lazy-loaded relationships fail in async context. PostGIS functions need to be called through `sqlalchemy.func`, not through geoalchemy2's convenience functions.

**Solution**:
- `expire_on_commit=False` on session factory prevents post-commit lazy loads
- `selectinload()` on queries that need relationships
- Use `sqlalchemy.func.ST_DWithin()` instead of geoalchemy2 convenience functions
- Separate transactions for report creation and case linking to isolate failures

### Challenge 5: Conversation State Persistence

**Problem**: Long-running conversations may span hours or days. State must survive API restarts, worker crashes, and user disconnections.

**Solution**: Dual storage with different tradeoffs:
- **Redis** (primary): Fast read/write, TTL-based cleanup (24h state, 1h session)
- **PostgreSQL** (`conversation_states` table): Backup for important conversations

The `get_or_create_conversation` flow checks for completed/errored conversations and starts fresh ones, preventing stale state from affecting new reports.

### Challenge 6: Webhook Reliability

**Problem**: Telegram may retry webhook deliveries if not acknowledged quickly. Long-running LLM calls could cause webhook timeouts.

**Solution**: Immediate acknowledgment + async processing:
1. Webhook handler receives message
2. Immediately queues to Redis Stream (`queue_incoming_message`)
3. Returns 200 to Telegram within milliseconds
4. Worker processes asynchronously from the stream

This decoupling ensures Telegram never times out waiting for the LLM.

### Challenge 7: Outbreak Detection at Scale

**Problem**: As report volume grows, checking every new report against all existing reports for case linking becomes expensive.

**Solution**:
- PostGIS `ST_DWithin` with GiST index — spatial filtering is O(log n)
- Time-window filtering (only check reports within threshold window, e.g., 7 days)
- Symptom array overlap (`&&` operator) eliminates non-matching reports before Jaccard calculation
- Separate transaction with `begin_nested()` savepoint for duplicate link handling

---

## Appendix: Quick Reference

### Key File Locations

| What | Where |
|------|-------|
| LangGraph workflow | `cbi/agents/graph.py` |
| State schema | `cbi/agents/state.py` |
| Reporter Agent | `cbi/agents/reporter.py` |
| Surveillance Agent | `cbi/agents/surveillance.py` |
| Analyst Agent | `cbi/agents/analyst.py` |
| System prompts | `cbi/agents/prompts.py` |
| Database models | `cbi/db/models.py` |
| Database queries | `cbi/db/queries.py` |
| FastAPI app | `cbi/api/main.py` |
| Redis state service | `cbi/services/state.py` |
| Message queue | `cbi/services/message_queue.py` |
| Real-time pub/sub | `cbi/services/realtime.py` |
| Auth (JWT + bcrypt) | `cbi/services/auth.py` |
| Messaging gateway | `cbi/services/messaging/base.py` |
| Telegram gateway | `cbi/services/messaging/telegram.py` |
| Background worker | `cbi/workers/main.py` |
| Settings | `cbi/config/settings.py` |
| LLM configs | `cbi/config/llm_config.py` |
| PII-safe logging | `cbi/config/logging.py` |

### Environment Variables (Required)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `ANTHROPIC_API_KEY` | Claude API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `JWT_SECRET` | 256-bit secret for JWT (min 32 chars) |
| `ENCRYPTION_KEY` | 32-byte key for AES-256 |
| `PHONE_HASH_SALT` | Salt for phone number hashing |

### MoH Threshold Quick Reference

| Disease | Alert At | Outbreak At | Window | Any Death = Critical |
|---------|----------|-------------|--------|---------------------|
| Cholera | 1 case | 3 cases | 7 days | Yes |
| Dengue | 5 cases | 20 cases | 7 days | Yes |
| Malaria | 10 cases | 50 cases | 7 days | No |
| Measles | 1 case | 5 cases | 14 days | Yes |
| Meningitis | 1 case | 3 cases | 7 days | Yes |
