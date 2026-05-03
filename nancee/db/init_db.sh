#!/bin/bash

DB_PATH="/nancee/db/nancee.db"
SCHEMA_PATH="$(dirname "$0")/create_tables.sql"

echo "Rebuilding Nancee DB..."

# Stop if DB is in use (optional safety)
lsof "$DB_PATH" && echo "DB in use, aborting" && exit 1

# Remove old DB
rm -f "$DB_PATH"

# Recreate DB from schema
sqlite3 "$DB_PATH" < "$SCHEMA_PATH"

echo "DB created at $DB_PATH"
