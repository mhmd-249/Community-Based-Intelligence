# Implement Feature

Implement the feature described below following CBI project standards.

## Feature Request
$ARGUMENTS

## Implementation Checklist

Follow this process:

### 1. Understand Requirements
- Review the feature request carefully
- Check CLAUDE.md for relevant architecture context
- Identify which components need changes (agents, api, services, db)
- List any new dependencies needed

### 2. Plan the Implementation
Before writing code, outline:
- Files to create or modify
- Database changes needed (if any)
- API endpoint changes (if any)
- State changes (if any)

### 3. Implement with Tests
For each component:
- Write the implementation with full type hints
- Create corresponding unit tests
- Follow the existing code patterns in the codebase

### 4. Code Standards
Ensure all code follows these standards:
- Python 3.11+ features
- Async/await for I/O operations
- Pydantic for data validation
- Type hints on all functions
- Docstrings on public functions
- Structured logging (no PII)
- Custom exceptions in exceptions.py

### 5. Security Considerations
- Never log sensitive data (phone numbers, PII)
- Validate all inputs
- Use parameterized queries
- Check authentication/authorization

### 6. Arabic Language Support
- Test with Arabic input if the feature handles user text
- Ensure UI strings support RTL if applicable

### 7. Final Checks
- Run linting: `ruff check .`
- Run type checking: `mypy .`
- Run tests: `pytest`
- Update CLAUDE.md if architecture changed

## Output Format
1. First, show your implementation plan
2. Then create/modify files one by one
3. Create tests alongside implementation
4. Summarize changes at the end
