#!/bin/bash

# This script sets up PostgreSQL locally for the chat app.
# It creates a user and database for local development.

# Check if psql command exists
if ! command -v psql &> /dev/null
then
    echo "psql could not be found. Please install PostgreSQL first."
    exit 1
fi

# Start PostgreSQL service (adjust for your OS)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sudo service postgresql start
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew services start postgresql
else
    echo "Please start PostgreSQL service manually."
fi

# Variables - change these as needed
DB_USER="chatuser"
DB_PASSWORD="chatpassword"
DB_NAME="chatdb"

# Create user and database
echo "Creating PostgreSQL user and database..."

sudo -u postgres psql <<EOF
DO
\$do\$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}'
   ) THEN
      CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
   END IF;
END
\$do\$;

CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
EOF

echo "PostgreSQL setup complete."
echo "Update your .env file with:"
echo "DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}"
