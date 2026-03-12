#!/bin/bash
# Database Size Collector - Installation Script
# Run this on the server where the collector will run

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Database Size Collector Installation"
echo "=========================================="

# Check Python
echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 is not installed"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
echo "Found: $PYTHON_VERSION"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" || {
    echo "WARNING: pip install failed, trying with --user"
    pip3 install --user -r "$SCRIPT_DIR/requirements.txt"
}

# Make scripts executable
echo ""
echo "Making scripts executable..."
chmod +x "$SCRIPT_DIR"/*.py
chmod +x "$SCRIPT_DIR"/*.sh

# Create log directory
echo ""
echo "Setting up logging..."
LOG_DIR="/var/log"
if [ -w "$LOG_DIR" ]; then
    touch "$LOG_DIR/db_size_collector.log" 2>/dev/null || true
    echo "Log file: $LOG_DIR/db_size_collector.log"
else
    echo "WARNING: Cannot write to $LOG_DIR, using local logging"
fi

# Validate configuration
echo ""
echo "Validating configuration..."
if [ ! -f "$SCRIPT_DIR/config.py" ]; then
    echo "ERROR: config.py not found!"
    exit 1
fi

# Secure config file
chmod 600 "$SCRIPT_DIR/config.py"
echo "Config file secured (chmod 600)"

# Test inventory parser
echo ""
echo "Testing inventory parser..."
INVENTORY_PATH="$SCRIPT_DIR/../ansible/inventory/mtn_databases"
if [ -d "$INVENTORY_PATH" ]; then
    python3 "$SCRIPT_DIR/inventory_parser.py" "$INVENTORY_PATH"
else
    echo "WARNING: Inventory path not found: $INVENTORY_PATH"
    echo "         Please update INVENTORY_PATH in config.py"
fi

# Oracle schema reminder
echo ""
echo "=========================================="
echo "IMPORTANT: Oracle Schema Setup Required"
echo "=========================================="
echo ""
echo "Run the following to create Oracle tables:"
echo ""
echo "  sqlplus dba_db_size/AlirEza_1234Bdas@127.0.0.1:1521/ORCL"
echo "  @$SCRIPT_DIR/schema.sql"
echo ""

# Cron setup instructions
echo "=========================================="
echo "Cron Setup"
echo "=========================================="
echo ""
echo "Add to crontab (crontab -e):"
echo ""
echo "  # Database Size Collection - Daily at 2:00 AM"
echo "  0 2 * * * $SCRIPT_DIR/run_collector.sh >> /var/log/db_size_collector_cron.log 2>&1"
echo ""

# Test command
echo "=========================================="
echo "Test Command"
echo "=========================================="
echo ""
echo "Run a dry-run test:"
echo ""
echo "  python3 $SCRIPT_DIR/collect_db_sizes.py --dry-run --verbose"
echo ""

echo "Installation complete!"
