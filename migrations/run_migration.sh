#!/bin/bash
# TBNManager Database Migration Script
# Run this on the R730 after MySQL container is set up

# Configuration
MYSQL_CONTAINER="tbnmanager-mysql"
MYSQL_USER="tbnbot"
MYSQL_PASSWORD="TBN_BotPass_2024"
MYSQL_DATABASE="tbnmanager"

echo "=========================================="
echo "TBNManager Database Migration"
echo "=========================================="

# Check if container is running
if ! docker ps | grep -q "$MYSQL_CONTAINER"; then
    echo "ERROR: MySQL container '$MYSQL_CONTAINER' is not running!"
    echo "Start it with: docker start $MYSQL_CONTAINER"
    exit 1
fi

echo "MySQL container is running."

# Run migration
echo "Running migration 001_initial_schema.sql..."
docker exec -i "$MYSQL_CONTAINER" mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" < 001_initial_schema.sql

if [ $? -eq 0 ]; then
    echo "=========================================="
    echo "Migration completed successfully!"
    echo "=========================================="

    # Show table count
    echo ""
    echo "Tables created:"
    docker exec "$MYSQL_CONTAINER" mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SHOW TABLES;"
else
    echo "=========================================="
    echo "ERROR: Migration failed!"
    echo "=========================================="
    exit 1
fi
