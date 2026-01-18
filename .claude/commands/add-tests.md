# Add Tests

Add comprehensive tests for: $ARGUMENTS

## Testing Strategy

### Backend (pytest)
1. **Unit Tests** (services, utils)
   - Mock external dependencies
   - Test happy paths and edge cases
   - Test error conditions

2. **Integration Tests** (API endpoints)
   - Use test database
   - Test request validation
   - Test response format
   - Test authentication/authorization

3. **Test Structure**
   ```
   tests/
   ├── conftest.py          # Fixtures
   ├── unit/
   │   ├── services/
   │   └── utils/
   └── integration/
       └── api/
   ```

### Frontend (Jest + React Testing Library)
1. **Component Tests**
   - Render correctly
   - User interactions work
   - Loading/error states

2. **Hook Tests**
   - Custom hooks behave correctly

## Requirements
- Use pytest fixtures for setup/teardown
- Use factories for test data (factory_boy)
- Mock external APIs (Claude, Supabase)
- Test async functions properly
- Aim for meaningful assertions, not just coverage

## Output
1. Create test files following project structure
2. Include fixtures needed
3. Run tests and report results
4. Note any gaps in testability
