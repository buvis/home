# Database Migration Management

Manages database schema migrations with safety checks and rollback capabilities.

## Usage
```
/db-migrate [action: create|up|down|status|validate]
```

## Process

1. **Analyze Current State**:
   - Examine current database schema and structure
   - Detect schema changes needed from code changes
   - Identify migration dependencies and order
   - Check for existing migration files and history

2. **Generate Migration Files**:
   - Create migration scripts with up/down operations
   - Include data transformations and index changes
   - Add foreign key constraints and relationship updates
   - Generate rollback procedures for safe reversions

3. **Validate Migration Safety**:
   - Test migrations on development database copy
   - Check for data integrity issues and conflicts
   - Validate performance impact of schema changes
   - Ensure backward compatibility during deployments

4. **Execute with Safety Checks**:
   - Create database backup before migration
   - Apply migrations with transaction safety
   - Monitor migration progress and performance
   - Verify data integrity after completion

5. **Monitor & Document**:
   - Track migration execution time and impact
   - Document schema changes and rationale
   - Create rollback procedures and emergency plans
   - Update database documentation and team knowledge

Ensures safe, reliable database schema evolution with zero-downtime deployment capabilities.