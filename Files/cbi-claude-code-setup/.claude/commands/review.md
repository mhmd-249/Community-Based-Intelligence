# Code Review

Review the specified code for issues, improvements, and adherence to CBI project standards.

## Files to Review
$ARGUMENTS

## Review Checklist

Analyze the code for:

### 1. Correctness
- [ ] Logic errors or bugs
- [ ] Edge cases not handled
- [ ] Error handling completeness
- [ ] Async/await correctness
- [ ] Resource cleanup (connections, files)

### 2. Security
- [ ] PII logging (phone numbers should NEVER appear in logs)
- [ ] SQL injection vulnerabilities
- [ ] Input validation
- [ ] Authentication/authorization checks
- [ ] Secrets in code (should be in environment)
- [ ] Phone number handling (hash for lookup, encrypt for storage)

### 3. Performance
- [ ] N+1 queries
- [ ] Missing database indexes
- [ ] Unnecessary API calls
- [ ] Large data in memory
- [ ] Missing pagination
- [ ] Redis key patterns efficiency

### 4. Code Quality
- [ ] Type hints present and correct
- [ ] Docstrings on public functions
- [ ] Consistent naming conventions
- [ ] Code duplication
- [ ] Function length (prefer < 50 lines)
- [ ] Import organization

### 5. CBI-Specific Standards
- [ ] Follows CLAUDE.md architecture
- [ ] Uses correct LLM models (Haiku for Reporter, Sonnet for Surveillance/Analyst)
- [ ] Conversation state handled correctly
- [ ] Arabic language support considered
- [ ] Empathetic but concise agent responses

### 6. Testing
- [ ] Unit tests exist for new functions
- [ ] Edge cases tested
- [ ] Mocks used appropriately
- [ ] Test coverage adequate

### 7. Documentation
- [ ] Complex logic explained
- [ ] API endpoints documented
- [ ] Configuration documented

## Output Format

For each issue found, provide:

```
**[SEVERITY: Critical/High/Medium/Low]** Issue Title

Location: filename:line_number

Problem: Clear description of the issue

Current code:
\`\`\`python
# problematic code
\`\`\`

Suggested fix:
\`\`\`python
# improved code
\`\`\`

Rationale: Why this change is important
```

## Summary

After reviewing, provide:
1. Total issues by severity
2. Most critical issues to address first
3. Overall code health assessment
4. Positive observations (what's done well)
