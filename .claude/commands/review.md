# Code Review

Review the recent changes or specified files: $ARGUMENTS

## Review Checklist
1. **Code Quality**
   - Clean, readable code
   - Proper naming conventions
   - No code duplication
   - Functions are focused (single responsibility)

2. **Type Safety**
   - All Python functions have type hints
   - TypeScript strict mode compliance
   - Pydantic models properly defined

3. **Error Handling**
   - Appropriate exceptions raised
   - Errors logged properly
   - User-friendly error messages

4. **Security**
   - No hardcoded secrets
   - Input validation present
   - SQL injection prevention (parameterized queries)
   - Auth checks on protected endpoints

5. **Performance**
   - No N+1 queries
   - Proper async usage
   - Efficient database queries

6. **Testing**
   - Tests exist for new functionality
   - Edge cases covered
   - Tests are meaningful (not just coverage)

7. **Documentation**
   - Docstrings on public functions
   - Complex logic explained
   - API endpoints documented

## Output
Provide:
1. Summary of findings
2. Critical issues (must fix)
3. Suggestions (nice to have)
4. Specific code improvements with examples
