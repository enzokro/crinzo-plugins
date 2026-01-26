#!/bin/bash
# tests/integration/test_memory_flow.sh
# Run: bash tests/integration/test_memory_flow.sh
#
# Integration test for the new memory type expansion and observer module.
# Tests the full flow from storing new types to context building.

set -e
HELIX="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=== Helix Memory Flow Integration Test ==="
echo "HELIX_ROOT: $HELIX"
echo ""

# Use a test database
export HELIX_DB_PATH="${HELIX}/tests/integration/test_memory.db"
rm -f "$HELIX_DB_PATH"

echo "=== 1. Testing New Memory Types ==="
echo "Storing fact..."
python3 "$HELIX/lib/memory/core.py" store \
    --type fact \
    --trigger "Auth system uses JWT tokens in src/auth/" \
    --resolution "JWT handling in jwt.py, middleware in middleware.py" \
    --source "test"

echo "Storing convention..."
python3 "$HELIX/lib/memory/core.py" store \
    --type convention \
    --trigger "All API calls go through utils/api.ts" \
    --resolution "Centralized error handling and auth headers" \
    --source "test"

echo "Storing decision..."
python3 "$HELIX/lib/memory/core.py" store \
    --type decision \
    --trigger "Using SQLite for local development" \
    --resolution "Simplicity over Postgres for dev environment" \
    --source "test"

echo "Storing evolution..."
python3 "$HELIX/lib/memory/core.py" store \
    --type evolution \
    --trigger "Session: Add user authentication" \
    --resolution "Completed 3/3 tasks. Added JWT, middleware, tests" \
    --source "test"

echo ""
echo "=== 2. Testing Recall by Type ==="
echo "Recalling facts about authentication..."
python3 "$HELIX/lib/memory/core.py" recall "authentication" --type fact --limit 3

echo ""
echo "Recalling conventions about API..."
python3 "$HELIX/lib/memory/core.py" recall "API" --type convention --limit 3

echo ""
echo "Recalling by multiple types..."
python3 "$HELIX/lib/memory/core.py" recall-by-type "authentication" --types "fact,convention,decision"

echo ""
echo "=== 3. Testing Observer Module ==="
echo "Testing explorer observation..."
python3 "$HELIX/lib/observer.py" explorer --output '{
    "scope": "src/",
    "findings": [
        {"file": "src/db/models.py", "what": "SQLAlchemy models", "relevance": "high", "context": "ORM models for users, sessions"},
        {"file": "src/utils/helpers.py", "what": "Helper functions", "relevance": "low"}
    ],
    "framework": {"detected": "FastAPI", "confidence": "HIGH", "evidence": "Found main.py with FastAPI imports"}
}'

echo ""
echo "Testing builder observation..."
python3 "$HELIX/lib/observer.py" builder \
    --task '{"id": "task-001", "subject": "001: add-auth", "description": "Add authentication"}' \
    --result '{"status": "delivered", "summary": "Added JWT authentication following the repository pattern"}' \
    --files-changed '["src/auth/jwt.py", "src/auth/middleware.py"]'

echo ""
echo "Testing session observation..."
python3 "$HELIX/lib/observer.py" session \
    --objective "Add user authentication" \
    --tasks '[{"id": "t1", "subject": "001: setup"}, {"id": "t2", "subject": "002: impl"}]' \
    --outcomes '{"t1": "delivered", "t2": "delivered"}'

echo ""
echo "=== 4. Testing Context Builders ==="
echo "Testing explorer context..."
python3 "$HELIX/lib/context.py" build-explorer-context --objective "Add new feature" --scope "src/auth"

echo ""
echo "Testing planner context..."
python3 "$HELIX/lib/context.py" build-planner-context --objective "Add new API endpoint"

echo ""
echo "=== 5. Health Check ==="
python3 "$HELIX/lib/memory/core.py" health

echo ""
echo "=== Cleanup ==="
rm -f "$HELIX_DB_PATH"

echo ""
echo "=== All integration tests passed! ==="
