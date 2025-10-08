# API Documentation Generation

Generates comprehensive API documentation from code and specifications.

## Usage
```
/api-docs [type: openapi|graphql|rest|grpc]
```

## Process

1. **Analyze Codebase**:
   - Scan for API endpoints, routes, and handlers
   - Identify GraphQL schemas, gRPC services, or REST APIs
   - Extract parameter types, response formats, and examples
   - Detect authentication and authorization patterns

2. **Generate Documentation**:
   - Create OpenAPI/Swagger specifications
   - Build GraphQL schema documentation
   - Generate REST API references with examples
   - Include authentication flows and error responses

3. **Format Output**:
   - Generate interactive documentation (Swagger UI, GraphiQL)
   - Create markdown documentation for repositories
   - Export to multiple formats (HTML, PDF, JSON)
   - Include code examples in multiple languages

4. **Validate & Test**:
   - Verify documentation completeness
   - Test example requests and responses
   - Check for broken links and references
   - Validate schema compliance

Creates professional API documentation that stays synchronized with code changes.