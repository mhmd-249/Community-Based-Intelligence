# CBI Implementation Guide

> Step-by-step prompts for building CBI with Claude Code

## How to Use This Guide

1. **Start Claude Code** in your project directory: `claude`
2. **Work through phases sequentially** - each builds on the previous
3. **Copy the prompt** from each section and paste into Claude Code
4. **Review the output** before moving to the next prompt
5. **Use `/clear`** between major phases to reset context

**Pro Tips:**
- Press `Escape` twice to see message history
- Use `@filename` to reference specific files in follow-up questions
- If output is incomplete, say "continue" or "finish the implementation"
- For large files, Claude Code may create them incrementally

---

## Phase 1: Project Foundation (Week 1)

### 1.1 Initialize Project Structure

**Copy this prompt:**

```
Initialize a Python project for a multi-agent health surveillance system called "CBI" (Community Based Intelligence).

Create the following:

1. pyproject.toml with these dependencies:
   - fastapi, uvicorn[standard], httpx
   - langgraph, anthropic
   - sqlalchemy[asyncio], asyncpg, alembic
   - redis, python-jose[cryptography], passlib[bcrypt]
   - pydantic, pydantic-settings
   - structlog (for logging)
   - pytest, pytest-asyncio, pytest-cov (dev)
   - ruff, mypy (dev)

2. The complete project directory structure as specified in CLAUDE.md

3. A basic config/settings.py using Pydantic Settings that loads from environment variables (see CLAUDE.md for required variables)

4. A config/logging.py with JSON structured logging that:
   - Never logs PII (phone numbers, etc.)
   - Includes conversation_id and agent name in log context
   - Outputs in JSON format for production

5. An empty __init__.py in each package directory

Use Python 3.11+ features. Include type hints on all functions.
```

### 1.2 Docker Development Environment

**Copy this prompt:**

```
Create Docker configuration for local development:

1. Dockerfile for the Python backend:
   - Multi-stage build (builder + runtime)
   - Python 3.11-slim base
   - Non-root user for security
   - Install dependencies from pyproject.toml

2. docker-compose.yml with services:
   - api: FastAPI app on port 8000, hot reload enabled, mounts ./src
   - worker: Background worker for processing messages
   - db: PostgreSQL 15 with PostGIS 3.3, persistent volume, init script mount
   - redis: Redis 7 Alpine, persistent volume
   - ngrok: For Telegram webhook tunneling (use ngrok/ngrok image)

3. docker-compose.override.yml.example for local customization

4. .dockerignore file

Configure the API and worker services to:
- Wait for db and redis to be healthy before starting
- Use environment variables from .env file
- Share the same network for inter-service communication

Include health checks for db and redis services.
```

### 1.3 Database Schema and Migrations

**Copy this prompt:**

```
Create the complete database schema for CBI:

1. migrations/001_initial_schema.sql with:
   - Enable extensions: uuid-ossp, postgis, pgcrypto
   - All ENUM types from CLAUDE.md (report_status, urgency_level, alert_type, disease_type, reporter_rel, link_type)
   - All tables: reporters, officers, reports, report_links, notifications, audit_logs
   - All indexes for performance (especially GIST index on location_point)
   - Trigger for auto-updating updated_at

2. db/models.py with SQLAlchemy 2.0 async models:
   - Use mapped_column syntax
   - Include relationships
   - Use GeoAlchemy2 for PostGIS Geography type

3. db/session.py with:
   - Async engine creation
   - AsyncSession factory
   - Context manager for sessions
   - init_db() and close_db() functions for app lifecycle

4. alembic.ini and alembic/env.py configured for async SQLAlchemy

Follow the exact schema from CLAUDE.md. Include all fields and constraints.
```

### 1.4 Basic FastAPI Application

**Copy this prompt:**

```
Create the FastAPI application skeleton:

1. api/main.py with:
   - Lifespan context manager for startup/shutdown (init DB, Redis)
   - CORS middleware configured from settings
   - Custom middleware imports (we'll implement later)
   - Router includes for all route modules
   - Health check endpoint returning {"status": "healthy", "version": "1.0.0"}

2. api/deps.py with dependency injection:
   - get_db() - yields async database session
   - get_redis() - yields Redis connection
   - get_current_officer() - JWT authentication (placeholder for now)

3. api/schemas/ with Pydantic models:
   - reports.py: ReportCreate, ReportUpdate, ReportResponse, ReportListResponse
   - notifications.py: NotificationResponse, NotificationListResponse
   - auth.py: LoginRequest, TokenResponse, OfficerResponse

4. api/routes/ with placeholder routers:
   - webhook.py: POST /telegram, POST /whatsapp, GET /whatsapp (verification)
   - reports.py: GET /, GET /{id}, PATCH /{id}, POST /{id}/notes
   - notifications.py: GET /, POST /{id}/read
   - analytics.py: POST /query, POST /visualize
   - auth.py: POST /login, POST /refresh, GET /me

Each route should return a placeholder response for now. We'll implement the logic in later phases.
```

---

## Phase 2: Messaging Gateway (Week 2)

### 2.1 Abstract Messaging Interface

**Copy this prompt:**

```
Create the messaging gateway abstraction layer:

1. services/messaging/base.py with:
   - @dataclass IncomingMessage: platform, message_id, chat_id, from_id, text, timestamp, reply_to_id
   - @dataclass OutgoingMessage: chat_id, text, reply_to_id
   - Abstract class MessagingGateway with methods:
     - async send_message(message: OutgoingMessage) -> str (returns message_id)
     - async send_template(chat_id, template_name, params) -> str
     - parse_webhook(data: dict) -> list[IncomingMessage]

2. services/messaging/telegram.py implementing MessagingGateway:
   - Use httpx.AsyncClient for API calls
   - Implement send_message with HTML parse mode
   - Implement send_template using formatted strings (Telegram doesn't have templates)
   - Implement parse_webhook to extract text messages from Telegram update format
   - Handle photo/document messages gracefully (log and skip for MVP)

3. services/messaging/whatsapp.py implementing MessagingGateway:
   - Implement for WhatsApp Cloud API format
   - send_template must use WhatsApp's template message format
   - parse_webhook handles the nested WhatsApp webhook structure

4. services/messaging/factory.py:
   - get_gateway(platform: str) -> MessagingGateway
   - Cache gateway instances (singleton per platform)

Include proper error handling with custom exceptions.
```

### 2.2 Webhook Handlers

**Copy this prompt:**

```
Implement the webhook handlers in api/routes/webhook.py:

1. POST /telegram endpoint:
   - Accept JSON body (Telegram Update object)
   - Validate it's a message (not edit, callback, etc.)
   - Extract using TelegramGateway.parse_webhook()
   - Queue message to Redis Stream for async processing (use background task for now)
   - Return {"ok": true} immediately (Telegram requires fast response)

2. POST /whatsapp endpoint:
   - Verify X-Hub-Signature-256 header using HMAC-SHA256
   - Parse message using WhatsAppGateway.parse_webhook()
   - Queue to Redis Stream
   - Return {"status": "ok"}

3. GET /whatsapp endpoint (verification):
   - Check hub.mode == "subscribe"
   - Verify hub.verify_token matches settings
   - Return hub.challenge as integer

4. Create services/message_queue.py with:
   - queue_incoming_message(message: IncomingMessage) - adds to Redis Stream
   - consume_messages() - generator that yields messages from stream
   - Use consumer groups for reliable processing

Implement proper logging (structured, no PII). Include signature verification helper function.
```

### 2.3 Telegram Bot Setup Script

**Copy this prompt:**

```
Create a setup script for Telegram bot configuration:

scripts/setup_telegram.py that:

1. Uses the Telegram Bot API to:
   - Get bot info (getMe) and display bot username
   - Set webhook URL (setWebhook) to the configured TELEGRAM_WEBHOOK_URL
   - Set bot commands (setMyCommands) with:
     - /start - Start reporting a health incident
     - /help - Get help with using this bot
     - /status - Check status of your recent report

2. Includes CLI arguments:
   - --set-webhook: Set the webhook URL
   - --delete-webhook: Remove webhook (for polling mode)
   - --info: Display bot info and current webhook status

3. Prints clear success/error messages

Also create a simple test script scripts/test_telegram.py that:
- Sends a test message to a specified chat_id
- Verifies the gateway is working correctly

Usage should be:
python scripts/setup_telegram.py --set-webhook
python scripts/test_telegram.py --chat-id 12345 --message "Test message"
```

---

## Phase 3: Reporter Agent (Weeks 3-4)

### 3.1 LangGraph State Definition

**Copy this prompt:**

```
Create the LangGraph state schema in agents/state.py:

1. Pydantic models for nested data:
   - Message: role (user/assistant/system), content, timestamp, message_id
   - ExtractedData: symptoms[], suspected_disease, location_text, location_normalized, location_coords, onset_text, onset_date, cases_count, deaths_count, affected_description, reporter_relationship
   - Classification: suspected_disease, confidence, data_completeness, urgency, alert_type, reasoning, recommended_actions[], follow_up_questions[]

2. TypedDict ConversationState with all fields:
   - Identifiers: conversation_id, reporter_phone, platform
   - Conversation: messages[], current_mode (listening/investigating/confirming/complete/error), language (ar/en/unknown)
   - Extracted data and classification
   - Control flow: pending_response, handoff_to, error
   - Metadata: created_at, updated_at, turn_count

3. Helper functions:
   - create_initial_state(conversation_id, phone, platform) -> ConversationState
   - get_missing_mvs_fields(extracted: ExtractedData) -> list[str]
   - calculate_data_completeness(extracted: ExtractedData) -> float

Use proper type hints and make sure all fields have sensible defaults.
```

### 3.2 State Management Service

**Copy this prompt:**

```
Create the state management service in services/state.py:

class StateService:

1. __init__: 
   - Initialize async Redis client
   - Set TTLs (state: 24 hours, session: 1 hour)

2. _phone_hash(phone: str) -> str:
   - SHA-256 hash with PHONE_HASH_SALT
   - Truncate to 16 chars for key efficiency

3. async get_or_create_conversation(platform, phone) -> tuple[ConversationState, bool]:
   - Check for existing session (session:{platform}:{phone_hash} -> conversation_id)
   - If exists, load and return state
   - If not, create new conversation with initial state
   - Return (state, is_new)

4. async get_state(conversation_id) -> Optional[ConversationState]:
   - Load from conversation:{conversation_id}
   - Handle JSON deserialization

5. async save_state(state: ConversationState):
   - Serialize and save with TTL
   - Extend session TTL

6. async delete_state(conversation_id):
   - Remove state and session keys

7. async extend_session(platform, phone):
   - Reset session TTL (for keeping conversation active)

Use Redis key patterns from CLAUDE.md. Handle connection errors gracefully.
```

### 3.3 Reporter Agent System Prompt

**Copy this prompt:**

```
Create agents/prompts.py with the Reporter Agent system prompt:

REPORTER_SYSTEM_PROMPT must include:

1. Identity and purpose:
   - Health incident reporting assistant for Sudan
   - Helps community members report health incidents naturally

2. Personality guidelines:
   - Empathetic but concise (responses under 50 words)
   - Never verbose or robotic - avoid "customer service bot" feel
   - Respond in user's language (Arabic or English)
   - One question at a time

3. Operating modes:
   - LISTENING MODE: Default, conversational, constantly evaluating for health signals
   - INVESTIGATION MODE: Triggered by health signals, collect MVS data

4. Health signals that SHOULD trigger investigation:
   - Current symptoms (vomiting, diarrhea, fever, bleeding, rash)
   - Disease names with current/local context
   - Deaths in community
   - Multiple people sick

5. Signals that should NOT trigger investigation:
   - Educational questions ("What are cholera symptoms?")
   - Past events ("I had malaria last year")
   - News/rumors without personal connection

6. MVS collection order:
   - WHAT: Symptoms or suspected disease
   - WHERE: Location (accept vague)
   - WHEN: Timing (accept imprecise)
   - WHO: Number affected, relationship

7. Template variables to inject:
   - {mode}: Current operating mode
   - {language}: Detected language
   - {extracted_data}: JSON of collected data
   - {missing_fields}: List of missing MVS fields

8. Tone examples (good and bad)

Also create SURVEILLANCE_SYSTEM_PROMPT and ANALYST_SYSTEM_PROMPT following the specifications in CLAUDE.md.
```

### 3.4 Reporter Agent Implementation

**Copy this prompt:**

```
Implement the Reporter Agent in agents/reporter.py:

1. Initialize Anthropic client with settings

2. async def reporter_node(state: ConversationState) -> ConversationState:
   
   a. Get latest user message
   
   b. Detect language if unknown (simple heuristic: Arabic chars = ar, else en)
   
   c. Build conversation history for Claude (role/content pairs)
   
   d. Format system prompt with current state variables
   
   e. Call Claude Haiku with:
      - Model from config
      - Temperature 0.3
      - Max tokens 500
      - System prompt
      - Messages history
   
   f. Parse response to detect:
      - Mode transition signals (use regex or structured output)
      - New extracted data (symptoms, location, etc.)
      - Confirmation signals
   
   g. Update state:
      - Append assistant message to history
      - Update current_mode if transition detected
      - Merge any newly extracted data
      - Set handoff_to = 'surveillance' if confirmed and complete
      - Set pending_response
      - Increment turn_count

3. Helper functions:
   - detect_language(text: str) -> str
   - parse_reporter_response(response, state) -> ConversationState
   - extract_data_from_response(response: str, state: ConversationState) -> ExtractedData

4. Use structured logging throughout (conversation_id, mode, turn_count)

Handle API errors gracefully - set error state and generate apologetic response.
```

### 3.5 LangGraph Workflow

**Copy this prompt:**

```
Create the LangGraph workflow in agents/graph.py:

1. Import all agent nodes and state

2. def create_cbi_graph():
   
   a. Initialize StateGraph with ConversationState
   
   b. Add nodes:
      - "reporter": reporter_node
      - "surveillance": surveillance_node (placeholder for now)
      - "analyst": analyst_node (placeholder for now)
      - "send_response": send_response_node
      - "send_notification": send_notification_node
   
   c. Set entry point to "reporter"
   
   d. Add conditional edges from reporter:
      - If error -> END
      - If handoff_to == 'surveillance' -> surveillance
      - If pending_response -> send_response
      - Else -> END
   
   e. Add edge: send_response -> END
   
   f. Add conditional edges from surveillance:
      - If urgency critical/high -> analyst
      - If urgency medium -> send_notification
      - Else -> END
   
   g. Add edges: analyst -> send_notification -> END
   
   h. Compile with checkpointer (use SqliteSaver for now, Redis in production)

3. async def send_response_node(state):
   - Get gateway for platform
   - Send pending_response to chat_id
   - Clear pending_response
   - Return updated state

4. async def send_notification_node(state):
   - Create notification in database
   - Publish to Redis pub/sub for real-time dashboard
   - Return state

5. Routing functions:
   - route_after_reporter(state) -> str
   - route_after_surveillance(state) -> str

Include proper error handling at each node.
```

### 3.6 Message Processing Worker

**Copy this prompt:**

```
Create the background worker in workers/main.py:

1. Main worker loop:
   - Consume messages from Redis Stream (with consumer group)
   - For each message:
     a. Parse IncomingMessage
     b. Load or create conversation state
     c. Append user message to state
     d. Run through LangGraph
     e. Save updated state
     f. Acknowledge message in stream

2. async def process_message(message: IncomingMessage):
   - Get or create state from StateService
   - Create Message object from incoming
   - Update state messages list
   - Get compiled graph
   - Run graph with state as input
   - Save final state
   - Log processing metrics (duration, mode, turn_count)

3. Consumer group setup:
   - Create group if not exists
   - Use worker_id for consumer name
   - Handle XPENDING for stuck messages

4. Graceful shutdown:
   - Handle SIGTERM/SIGINT
   - Finish current message before exiting
   - Close connections cleanly

5. Entry point:
   - Setup logging
   - Connect to Redis and DB
   - Run worker loop

Also create workers/health.py with a simple HTTP health endpoint for container orchestration.
```

---

## Phase 4: Surveillance Agent (Weeks 5-6)

### 4.1 Surveillance Agent Implementation

**Copy this prompt:**

```
Implement the Surveillance Agent in agents/surveillance.py:

1. Disease thresholds dictionary:
   THRESHOLDS = {
       'cholera': {'alert': 1, 'outbreak': 3, 'window_days': 7},
       'dengue': {'alert': 5, 'outbreak': 20, 'window_days': 7},
       'malaria': {'alert': 'baseline', 'outbreak': 'significant_deviation'},
       'clustered_deaths': {'alert': 2, 'outbreak': 5, 'window_days': 7}
   }

2. async def surveillance_node(state: ConversationState) -> ConversationState:
   
   a. Build classification request from extracted data
   
   b. Query for related cases (find_related_cases from db/queries.py):
      - Same geographic area
      - Within 7-day window
      - Similar symptoms
   
   c. Call Claude Sonnet with:
      - Surveillance system prompt
      - Report data
      - Related cases for context
      - Request JSON output
   
   d. Parse classification JSON:
      - suspected_disease
      - confidence
      - data_completeness
      - urgency
      - alert_type
      - reasoning
      - recommended_actions
      - follow_up_questions
   
   e. Check thresholds - upgrade urgency if exceeded
   
   f. Link cases - store relationships in report_links
   
   g. Create report in database
   
   h. Return updated state with classification

3. async def check_thresholds(classification, state, related_cases):
   - Count total cases (current + related)
   - Compare against disease thresholds
   - Upgrade urgency if needed
   - Add reasoning about threshold exceeded

4. Helper functions:
   - extract_json(text: str) -> dict
   - calculate_urgency(classification, total_cases) -> str
```

### 4.2 Case Linking Queries

**Copy this prompt:**

```
Implement geospatial and temporal case linking in db/queries.py:

1. async def find_related_cases(
    session,
    location: str,
    location_coords: Optional[tuple],
    symptoms: list[str],
    window_days: int = 7,
    radius_km: float = 10.0
) -> list[dict]:
   
   Use PostGIS ST_DWithin for geographic proximity:
   - If coords available: find reports within radius_km
   - If only text: fuzzy match on location_normalized
   
   Filter by:
   - created_at within window_days
   - status in ('open', 'investigating')
   
   Calculate symptom overlap score for each result
   
   Return list of dicts with: id, symptoms, suspected_disease, cases_count, created_at, symptom_overlap_score

2. async def get_case_count_for_area(
    session,
    location: str,
    disease: str,
    window_days: int
) -> int:
   - Count cases matching location and disease within window

3. async def link_reports(
    session,
    report_id_1: UUID,
    report_id_2: UUID,
    link_type: str,
    confidence: float
):
   - Create entry in report_links table
   - Handle duplicate constraint gracefully

4. async def get_linked_reports(session, report_id: UUID) -> list[dict]:
   - Get all reports linked to given report
   - Include link type and confidence

5. async def create_report(session, state: ConversationState) -> UUID:
   - Create or update reporter (by phone_hash)
   - Insert report with all extracted data
   - Return report ID

Include proper transaction handling and error recovery.
```

### 4.3 Notification Service

**Copy this prompt:**

```
Create the notification service in services/notifications.py:

1. async def create_notification(
    session,
    report_id: UUID,
    officer_id: Optional[UUID],
    urgency: str,
    classification: Classification
) -> UUID:
   
   a. Generate notification title based on disease and urgency
   b. Generate body with:
      - Case count
      - Location
      - Suspected disease
      - Key symptoms
      - Recommended actions
   c. Determine channels based on urgency:
      - critical: ['dashboard', 'whatsapp', 'email']
      - high: ['dashboard', 'email']
      - medium: ['dashboard']
   d. Insert notification record
   e. Return notification ID

2. async def send_notification(notification_id: UUID):
   - Load notification from DB
   - For each channel:
     - dashboard: Publish to Redis pub/sub
     - email: Queue email (implement later)
     - whatsapp: Send template message to officer

3. async def publish_to_dashboard(notification: dict):
   - Publish to Redis channel 'notifications:dashboard'
   - Include full notification data for real-time display

4. async def mark_as_read(session, notification_id: UUID, officer_id: UUID):
   - Update read_at timestamp
   - Log in audit_logs

5. async def get_unread_notifications(session, officer_id: UUID) -> list:
   - Get all notifications for officer where read_at is NULL
   - Order by urgency (critical first), then created_at

Generate notifications in both Arabic and English based on officer preference.
```

---

## Phase 5: Dashboard Backend (Weeks 7-8)

### 5.1 Authentication System

**Copy this prompt:**

```
Implement authentication in services/auth.py and api/routes/auth.py:

services/auth.py:
1. Password hashing with bcrypt (passlib)
2. JWT token creation with python-jose:
   - create_access_token(officer_id, role) -> str
   - create_refresh_token(officer_id) -> str
   - Access token expires in 24 hours
   - Refresh token expires in 7 days

3. Token verification:
   - verify_token(token) -> dict (payload)
   - Handle ExpiredSignatureError, InvalidTokenError

4. Current officer dependency:
   - async get_current_officer(credentials) -> Officer
   - Extract from Bearer token
   - Load officer from DB
   - Raise 401 if invalid or inactive

api/routes/auth.py:
1. POST /login:
   - Accept email and password
   - Verify against database
   - Return access_token, refresh_token, officer info

2. POST /refresh:
   - Accept refresh_token
   - Verify and issue new access_token

3. GET /me:
   - Require authentication
   - Return current officer profile

4. POST /logout (optional):
   - Invalidate refresh token (store in Redis blacklist)

Include rate limiting on login endpoint (5 attempts per minute per IP).
```

### 5.2 Reports API Implementation

**Copy this prompt:**

```
Implement the Reports API in api/routes/reports.py:

1. GET / (list reports):
   - Require authentication
   - Query parameters: status, urgency, disease, region, from_date, to_date, page, per_page
   - Filter by officer's region (unless admin)
   - Return paginated ReportListResponse
   - Include total count for pagination

2. GET /{report_id}:
   - Require authentication
   - Return full report details including:
     - All extracted data
     - Classification
     - Linked reports
     - Notifications history
     - Raw conversation (for debugging)
   - 404 if not found

3. PATCH /{report_id}:
   - Require authentication
   - Allowed updates: status, officer_id (assignment), investigation_notes, outcome
   - Log change in audit_logs
   - If status changes to 'resolved', set resolved_at

4. POST /{report_id}/notes:
   - Require authentication
   - Append to investigation_notes (keep history with timestamps)
   - Log in audit_logs

5. GET /{report_id}/linked:
   - Return all linked reports with link metadata

6. GET /{report_id}/timeline:
   - Return chronological timeline of:
     - Report creation
     - Status changes
     - Notifications sent
     - Notes added
     - Linked cases

Create corresponding db/queries.py functions for each operation.
```

### 5.3 WebSocket Real-time Updates

**Copy this prompt:**

```
Implement WebSocket support for real-time dashboard updates:

1. api/routes/websocket.py:
   
   @router.websocket("/ws")
   async def websocket_endpoint(websocket, token: str = Query(...)):
      - Verify JWT token from query param
      - Accept connection
      - Subscribe to Redis pub/sub channels:
        - notifications:{officer_id}
        - notifications:broadcast
        - reports:updates
      - Listen for messages and forward to WebSocket
      - Handle disconnection gracefully

2. services/realtime.py:
   
   class RealtimeService:
      - async publish_notification(notification_id, officer_ids):
        Publish to each officer's channel
      
      - async publish_report_update(report_id, update_type):
        Publish to reports:updates channel
      
      - async broadcast(message):
        Publish to broadcast channel

3. Update notification service to use RealtimeService after creating notification

4. Update report update logic to publish changes

5. Connection management:
   - Track connected clients (in Redis or memory)
   - Implement heartbeat/ping to detect stale connections
   - Clean up on disconnect

Message format for WebSocket:
{
    "type": "notification" | "report_update",
    "data": {...},
    "timestamp": "ISO8601"
}
```

---

## Phase 6: Analyst Agent (Weeks 9-10)

### 6.1 Natural Language Query Interface

**Copy this prompt:**

```
Implement the Analyst Agent query capability in agents/analyst.py:

1. async def analyst_node(state: ConversationState) -> ConversationState:
   - Called when surveillance triggers it (threshold exceeded)
   - Generate situation summary for notification

2. async def process_query(query: str, officer_id: UUID) -> dict:
   - Main entry point for natural language queries
   - Parse query intent
   - Generate and execute SQL
   - Format results

3. Query processing pipeline:
   
   a. async def parse_query_intent(query: str) -> dict:
      - Call Claude Sonnet to classify query type:
        - case_count: "How many cholera cases this week?"
        - trend: "Show me dengue trends in Khartoum"
        - comparison: "Compare cases this week vs last week"
        - geographic: "Where are the cholera hotspots?"
        - timeline: "When did the outbreak start?"
      - Extract parameters (disease, location, time range)
   
   b. async def generate_sql(intent: dict) -> str:
      - Use Claude to generate safe SQL query
      - Provide schema context
      - Request parameterized query (prevent injection)
   
   c. async def execute_query(sql: str, params: dict) -> list:
      - Execute with read-only connection
      - Timeout after 30 seconds
      - Log query in audit_logs
   
   d. async def format_results(results, intent) -> dict:
      - Generate human-readable summary
      - Include raw data for visualization

4. Security:
   - Whitelist allowed tables and columns
   - Validate generated SQL before execution
   - Use read-only database user
```

### 6.2 Visualization Generation

**Copy this prompt:**

```
Implement visualization code generation in agents/analyst.py:

1. async def generate_visualization(data: list, viz_type: str) -> str:
   - Call Claude Sonnet to generate visualization code
   - Supported types: line_chart, bar_chart, map, heatmap, timeline
   - Return JavaScript code for frontend execution

2. Visualization prompts for each type:
   
   LINE_CHART_PROMPT:
   - Generate Recharts LineChart component
   - Include proper axis labels and legend
   - Support multiple series
   
   BAR_CHART_PROMPT:
   - Generate Recharts BarChart component
   - Support stacked and grouped variants
   
   MAP_PROMPT:
   - Generate Leaflet map with markers
   - Color code by urgency
   - Include popup with case details
   
   HEATMAP_PROMPT:
   - Generate geographic heatmap
   - Show case density by region

3. async def generate_situation_summary(
    report_id: UUID,
    related_cases: list,
    classification: Classification
) -> str:
   - Generate comprehensive text summary for notification
   - Include:
     - Current situation overview
     - Case count and trend
     - Geographic spread
     - Risk assessment
     - Recommended immediate actions
   - Support both Arabic and English

4. api/routes/analytics.py endpoints:
   - POST /query: Execute natural language query
   - POST /visualize: Generate visualization for data
   - GET /summary/{report_id}: Get situation summary
```

---

## Phase 7: Testing (Weeks 11-12)

### 7.1 Unit Tests

**Copy this prompt:**

```
Create comprehensive unit tests in tests/unit/:

1. tests/unit/test_state.py:
   - Test create_initial_state()
   - Test get_missing_mvs_fields()
   - Test calculate_data_completeness()
   - Test state serialization/deserialization

2. tests/unit/test_crypto.py:
   - Test phone hashing (consistent output)
   - Test phone encryption/decryption (roundtrip)
   - Test different phone formats

3. tests/unit/test_language.py:
   - Test Arabic detection
   - Test English detection
   - Test mixed text handling

4. tests/unit/test_messaging.py:
   - Test Telegram webhook parsing
   - Test WhatsApp webhook parsing
   - Test OutgoingMessage formatting

5. tests/unit/test_prompts.py:
   - Test prompt formatting with variables
   - Test prompt length constraints

Use pytest fixtures for common test data. Mock external services.
```

### 7.2 Agent Tests with Golden Dataset

**Copy this prompt:**

```
Create agent tests with golden test cases in tests/agents/:

1. tests/agents/conftest.py:
   - Fixtures for mock Anthropic client
   - Fixtures for test conversation states
   - Helper to create mock LLM responses

2. tests/agents/test_reporter_intent.py:

   INTENT_TEST_CASES with cases that SHOULD trigger investigation:
   - "My neighbor has severe diarrhea since yesterday" (ar and en)
   - "Three children in my village are vomiting"
   - "Two people died from unknown illness"
   - "Many people sick with fever in Kassala"

   INTENT_TEST_CASES that should NOT trigger:
   - "What are the symptoms of cholera?"
   - "I had malaria last year"
   - "I heard there's disease in Egypt"
   - "How do I prevent dengue?"

   @pytest.mark.parametrize for each case
   Test that mode transitions correctly

3. tests/agents/test_reporter_extraction.py:
   - Test symptom extraction from various phrasings
   - Test location extraction (vague and specific)
   - Test number extraction ("three", "3", "a few")
   - Test Arabic number extraction

4. tests/agents/test_surveillance_classification.py:
   - Test disease classification accuracy
   - Test urgency assignment
   - Test threshold detection
   - Test case linking logic

5. tests/agents/test_full_conversation.py:
   - Test complete conversation flows
   - Simulate multi-turn conversations
   - Test conversation recovery after disconnect
```

### 7.3 Integration Tests

**Copy this prompt:**

```
Create integration tests in tests/integration/:

1. tests/integration/conftest.py:
   - Setup test database (use testcontainers)
   - Setup test Redis
   - Fixtures for test client
   - Database cleanup between tests

2. tests/integration/test_webhook_flow.py:
   - Test Telegram webhook -> message queue
   - Test WhatsApp webhook -> message queue
   - Test signature validation
   - Test malformed request handling

3. tests/integration/test_report_flow.py:
   - Test complete flow: webhook -> agent -> report
   - Test notification generation
   - Test database state after processing

4. tests/integration/test_api_reports.py:
   - Test GET /reports with filters
   - Test GET /reports/{id}
   - Test PATCH /reports/{id}
   - Test authentication required

5. tests/integration/test_api_auth.py:
   - Test login with valid credentials
   - Test login with invalid credentials
   - Test token refresh
   - Test rate limiting

6. tests/integration/test_database_queries.py:
   - Test find_related_cases with PostGIS
   - Test case count queries
   - Test report creation and linking

Use pytest-asyncio for async tests. Ensure tests are isolated and repeatable.
```

---

## Phase 8: Production Deployment (Week 13)

### 8.1 AWS Infrastructure

**Copy this prompt:**

```
Create Terraform configuration for AWS deployment in terraform/:

1. terraform/main.tf:
   - Provider configuration for AWS (eu-west-1)
   - S3 backend for state storage

2. terraform/vpc.tf:
   - VPC with CIDR 10.0.0.0/16
   - Public subnets for ALB
   - Private subnets for ECS tasks
   - Private data subnets for RDS/ElastiCache
   - NAT Gateway for outbound access
   - Security groups

3. terraform/ecs.tf:
   - ECS Cluster (Fargate)
   - Task definitions for API and Worker
   - Services with desired count
   - Auto-scaling policies
   - CloudWatch log groups

4. terraform/rds.tf:
   - RDS PostgreSQL 15 with PostGIS
   - db.t3.medium instance
   - Multi-AZ for production
   - Automated backups (7 days)
   - Security group (private access only)

5. terraform/elasticache.tf:
   - ElastiCache Redis cluster
   - cache.t3.micro for MVP
   - Security group

6. terraform/alb.tf:
   - Application Load Balancer
   - HTTPS listener with ACM certificate
   - Target groups for API

7. terraform/secrets.tf:
   - Secrets Manager for API keys
   - IAM roles for ECS task access

8. terraform/variables.tf and outputs.tf

Include comments explaining each resource.
```

### 8.2 Production Docker Configuration

**Copy this prompt:**

```
Create production-ready Docker configuration:

1. Dockerfile.prod (optimized for production):
   - Multi-stage build
   - Minimal runtime image
   - Non-root user
   - Health check
   - Security scanning labels

2. docker-compose.prod.yml:
   - Production-like local environment
   - No volume mounts
   - Resource limits
   - Logging configuration

3. .github/workflows/deploy.yml (GitHub Actions):
   - Build and push to ECR on main branch
   - Run tests before deploy
   - Deploy to ECS with rolling update
   - Notify on success/failure

4. scripts/deploy.sh:
   - Manual deployment script
   - Build, tag, push images
   - Update ECS service
   - Wait for stable deployment

5. scripts/rollback.sh:
   - Rollback to previous task definition

6. Monitoring configuration:
   - prometheus/prometheus.yml
   - grafana/dashboards/cbi.json
   - alertmanager/alertmanager.yml

Include all alert rules from CLAUDE.md.
```

---

## Custom Commands Reference

After completing the phases, use these slash commands for ongoing development:

- `/project:implement-feature` - Implement a new feature with tests
- `/project:review` - Review code for issues and improvements
- `/project:add-tests` - Add tests for existing code

See `.claude/commands/` for the command definitions.

---

## Tips for Success

1. **Don't rush** - Quality over speed. Review each output before proceeding.

2. **Ask follow-ups** - If output is incomplete, say "continue" or ask for specific parts.

3. **Test incrementally** - Run tests after each phase to catch issues early.

4. **Use version control** - Commit after each successful phase.

5. **Document as you go** - Update CLAUDE.md if you make architectural changes.

6. **Arabic testing** - Test Arabic inputs throughout, not just at the end.

7. **Monitor tokens** - Use `/clear` between phases to manage context window.

8. **Read the output** - Claude Code explains what it's doing. Learn from it.
