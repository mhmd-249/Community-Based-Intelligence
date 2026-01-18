# Add Tests

Generate comprehensive tests for the specified code following CBI testing standards.

## Code to Test
$ARGUMENTS

## Testing Strategy

### 1. Analyze the Code
- Identify all public functions and methods
- List input parameters and return types
- Find branching logic (if/else, match)
- Identify external dependencies to mock
- Note error conditions

### 2. Test Categories

#### Unit Tests (tests/unit/)
For pure functions and utilities:
- Test normal operation
- Test edge cases (empty inputs, None values, boundary conditions)
- Test error conditions
- Test type edge cases

#### Integration Tests (tests/integration/)
For database and external service interactions:
- Test with real database (testcontainers)
- Test transaction behavior
- Test query correctness
- Test connection handling

#### Agent Tests (tests/agents/)
For AI agent components:
- Use golden test cases (known inputs/outputs)
- Mock LLM responses
- Test mode transitions
- Test data extraction accuracy
- Test both Arabic and English inputs

### 3. CBI-Specific Test Cases

For Reporter Agent:
- Intent detection (should/should not trigger investigation)
- Language detection (Arabic/English/mixed)
- MVS extraction from various phrasings
- Conversation state transitions
- Timeout and error handling

For Surveillance Agent:
- Disease classification accuracy
- Urgency assignment
- Threshold detection
- Case linking logic

For API endpoints:
- Authentication required
- Input validation
- Pagination
- Error responses

### 4. Testing Patterns

```python
# Use fixtures for common setup
@pytest.fixture
def sample_conversation_state():
    return create_initial_state(
        conversation_id="test-123",
        phone="+249123456789",
        platform="telegram"
    )

# Use parametrize for multiple cases
@pytest.mark.parametrize("input_text,expected_mode", [
    ("My neighbor is sick", "investigating"),
    ("What is cholera?", "listening"),
])
async def test_intent_detection(input_text, expected_mode):
    ...

# Mock external services
@pytest.fixture
def mock_anthropic(mocker):
    mock = mocker.patch("anthropic.Anthropic")
    mock.return_value.messages.create.return_value = MockResponse(...)
    return mock

# Use testcontainers for database tests
@pytest.fixture
async def db_session():
    async with PostgresContainer("postgis/postgis:15-3.3") as postgres:
        yield await create_session(postgres.get_connection_url())
```

### 5. Test Data

Create realistic test data:
- Arabic text samples for language tests
- Various symptom descriptions
- Multiple location formats (village, city, landmark)
- Edge cases in numbers ("three", "3", "عدة")

### 6. Coverage Goals

- Unit tests: 80%+ coverage
- Agent tests: Cover all mode transitions
- API tests: Cover all endpoints and error cases
- Integration tests: Cover all database operations

## Output Format

1. Identify test file location based on source file
2. Create test file with:
   - Appropriate imports
   - Fixtures at the top
   - Tests organized by function/class
   - Clear test names describing what's tested
3. Include docstrings explaining complex test scenarios
4. Add any necessary conftest.py fixtures

## Example Test Structure

```python
"""Tests for services/state.py"""

import pytest
from unittest.mock import AsyncMock, patch
from services.state import StateService
from agents.state import create_initial_state


class TestStateService:
    """Tests for StateService class"""
    
    @pytest.fixture
    def state_service(self, mock_redis):
        return StateService(redis_client=mock_redis)
    
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()
    
    async def test_get_or_create_conversation_new(self, state_service, mock_redis):
        """Test creating a new conversation when none exists"""
        mock_redis.get.return_value = None
        
        state, is_new = await state_service.get_or_create_conversation(
            platform="telegram",
            phone="+249123456789"
        )
        
        assert is_new is True
        assert state["platform"] == "telegram"
        assert state["current_mode"] == "listening"
    
    async def test_get_or_create_conversation_existing(self, state_service, mock_redis):
        """Test returning existing conversation"""
        # ... test implementation
```
