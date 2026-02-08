#!/bin/bash
# Initialize database schema on Railway PostgreSQL
# Run once after first deployment:
#   railway run bash scripts/railway-init-db.sh

set -e

echo "Initializing FraudDetection database schema..."
psql "$DATABASE_URL" -f scripts/init_db.sql
echo "Database schema initialized successfully."
