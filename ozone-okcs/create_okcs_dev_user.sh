#!/bin/bash
# ============================================================================
# OKCS Dev Personal User Creation Script (v2.0)
# Creates MongoDB and MySQL users for developers on OKCS Dev environment
# 
# This script is designed to run from your LOCAL machine (gheshi) and uses
# SSH to execute commands on remote servers.
#
# Features:
#   - Automatically establishes SSH reverse tunnel for Kubernetes API
#   - Creates MongoDB user with specified role (RW/RO)
#   - Creates MySQL user via remote create_user_kuber.sh script
#   - Verifies both users were created successfully
#   - Check mode: verify if user exists (-c)
#   - Drop mode: delete existing user (-d)
#   - List mode: list all personal users (-l)
#   - Save credentials to file (-f)
#   - Trap cleanup on error
#
# Usage: 
#   ./create_okcs_dev_user.sh -u <username> -r <rw|ro> [options]
#
# Examples:
#   ./create_okcs_dev_user.sh -u e_alinaqizadeh -r rw        # Create RW user
#   ./create_okcs_dev_user.sh -u e_alinaqizadeh -r rw -f     # Create + save to file
#   ./create_okcs_dev_user.sh -u a_gheshlaghi_test -r rw -t  # Test mode
#   ./create_okcs_dev_user.sh -u e_alinaqizadeh -c           # Check if exists
#   ./create_okcs_dev_user.sh -u e_alinaqizadeh -d           # Drop user
#   ./create_okcs_dev_user.sh -l                             # List all users
#
# Author: Alireza Aghajanzadeh Gheshlaghi
# ============================================================================

set -euo pipefail

# Version
VERSION="2.0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Track if tunnel was established (for cleanup)
TUNNEL_ESTABLISHED=false

# Trap for cleanup on exit/error
cleanup_on_exit() {
    if [[ "$TUNNEL_ESTABLISHED" == "true" ]]; then
        pkill -f "R ${TUNNEL_LOCAL_PORT}:${K8S_API_HOST}:${K8S_API_PORT}.*${SSH_DB_HOST}" 2>/dev/null || true
    fi
}
trap cleanup_on_exit EXIT INT TERM

# ============================================================================
# CONFIGURATION
# ============================================================================

# SSH hosts
SSH_DB_HOST="oz-okcs-dev-db1"
SSH_MONGO_HOST="oz-okcs-dev-mongo1"

# SSH Tunnel configuration for Kubernetes API
TUNNEL_LOCAL_PORT="16443"
K8S_API_HOST="172.21.80.175"
K8S_API_PORT="443"

# MongoDB configuration
MONGO_HOST="okcs-dev-mongo.local"  # Corrected hostname for connection URI
MONGO_PORT="27017"
MONGO_ADMIN_USER="admin"
MONGO_ADMIN_PASS="ozone_okcs_dev_mongo_2024"
MONGO_DATABASES=("social" "third_party_proxy")

# Remote script for MySQL user creation
REMOTE_MYSQL_SCRIPT="/opt/db_scripts/create_user_kuber.sh"

# Credentials save directory
CREDS_DIR="${HOME}/.okcs_credentials"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${CYAN}[STEP $1]${NC} $2"
}

usage() {
    cat << EOF
OKCS Dev User Management Script v${VERSION}

Usage: $0 -u <username> -r <rw|ro> [options]
       $0 -l  (list users)

Operations:
  -u username   Username format: f_lastname (e.g., e_alinaqizadeh)
  -r <rw|ro>    Create user with role: 'rw' or 'ro'
  -c            Check if user exists (requires -u)
  -d            Drop/delete user (requires -u)
  -l            List all personal users

Options:
  -t            Test mode - creates user and then drops it
  -f            Save credentials to file (~/.okcs_credentials/)
  -h            Show this help message

Examples:
  $0 -u e_alinaqizadeh -r rw           # Create RW user
  $0 -u e_alinaqizadeh -r rw -f        # Create and save creds
  $0 -u a_gheshlaghi_test -r rw -t     # Test mode (create+drop)
  $0 -u e_alinaqizadeh -c              # Check if user exists
  $0 -u e_alinaqizadeh -d              # Drop user
  $0 -l                                # List all personal users

EOF
    exit 1
}

generate_mongo_password() {
    local username=$1
    local year=$(date +%Y)
    echo "${username}_okcs_dev_${year}"
}

# ============================================================================
# SSH TUNNEL FUNCTIONS
# ============================================================================

setup_ssh_tunnel() {
    log_info "Setting up SSH tunnel for Kubernetes API..."
    
    # Kill any existing tunnel on the remote side
    log_info "Cleaning up existing tunnel on remote server..."
    ssh "$SSH_DB_HOST" "sudo fuser -k ${TUNNEL_LOCAL_PORT}/tcp 2>/dev/null || true" 2>/dev/null || true
    
    # Kill any existing tunnel from our side
    pkill -f "R ${TUNNEL_LOCAL_PORT}:${K8S_API_HOST}:${K8S_API_PORT}.*${SSH_DB_HOST}" 2>/dev/null || true
    sleep 1
    
    # Establish new tunnel in background
    log_info "Establishing SSH reverse tunnel to ${SSH_DB_HOST}..."
    ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -R ${TUNNEL_LOCAL_PORT}:${K8S_API_HOST}:${K8S_API_PORT} \
        "$SSH_DB_HOST" -f -N
    
    sleep 2
    
    # Verify tunnel is working
    log_info "Verifying tunnel connectivity..."
    local test_result
    test_result=$(ssh "$SSH_DB_HOST" "curl -sk --connect-timeout 5 https://localhost:${TUNNEL_LOCAL_PORT}/version 2>&1" || echo "FAILED")
    
    if echo "$test_result" | grep -q "major\|minor"; then
        log_success "SSH tunnel established and verified"
        TUNNEL_ESTABLISHED=true
        return 0
    elif echo "$test_result" | grep -q "FAILED"; then
        log_error "Tunnel verification failed. Check network connectivity."
        return 1
    else
        log_warning "Tunnel test returned unexpected result, but continuing..."
        TUNNEL_ESTABLISHED=true
        return 0
    fi
}

# ============================================================================
# MONGODB FUNCTIONS (via SSH to mongo server)
# ============================================================================

create_mongodb_user() {
    local username=$1
    local password=$2
    local role=$3  # rw or ro
    
    log_info "Creating MongoDB user: $username on $SSH_MONGO_HOST"
    
    local mongo_role
    if [[ "$role" == "rw" ]]; then
        mongo_role="readWrite"
    else
        mongo_role="read"
    fi
    
    # Build roles JSON
    local roles_json="["
    local first=true
    for db in "${MONGO_DATABASES[@]}"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            roles_json+=","
        fi
        roles_json+="{role: \"$mongo_role\", db: \"$db\"}"
    done
    roles_json+="]"
    
    # Execute via SSH - use single quotes inside eval to avoid quoting issues
    ssh "$SSH_MONGO_HOST" "mongosh --quiet -u '$MONGO_ADMIN_USER' -p '$MONGO_ADMIN_PASS' --authenticationDatabase admin --eval '
try { db.getSiblingDB(\"admin\").dropUser(\"$username\"); } catch(e) {}
db.getSiblingDB(\"admin\").createUser({
  user: \"$username\",
  pwd: \"$password\",
  roles: [$(for db in "${MONGO_DATABASES[@]}"; do echo -n "{role: \"$mongo_role\", db: \"$db\"},"; done | sed 's/,$//' )]
});
print(\"MongoDB user $username created with $mongo_role\");
'" 2>&1
    
    if [[ $? -eq 0 ]]; then
        log_success "MongoDB user created: $username"
        return 0
    else
        log_error "Failed to create MongoDB user"
        return 1
    fi
}

drop_mongodb_user() {
    local username=$1
    
    log_info "Dropping MongoDB user: $username"
    
    ssh "$SSH_MONGO_HOST" "mongosh --quiet -u '$MONGO_ADMIN_USER' -p '$MONGO_ADMIN_PASS' --authenticationDatabase admin --eval \"
try { db.getSiblingDB('admin').dropUser('$username'); print('Dropped: $username'); } 
catch(e) { print('User not found: $username'); }
\"" 2>&1
    
    log_success "MongoDB user dropped: $username"
}

verify_mongodb_user() {
    local username=$1
    
    ssh "$SSH_MONGO_HOST" "mongosh --quiet -u '$MONGO_ADMIN_USER' -p '$MONGO_ADMIN_PASS' --authenticationDatabase admin --eval \"
var u = db.getSiblingDB('admin').getUser('$username');
if(u) { print('User: ' + u.user); u.roles.forEach(r => print('  - ' + r.role + ' on ' + r.db)); }
else { print('NOT FOUND'); }
\"" 2>&1
}

# ============================================================================
# CONNECTION VERIFICATION FUNCTIONS
# ============================================================================

test_mongodb_connection() {
    local username=$1
    local password=$2
    
    log_info "Testing MongoDB connection with new credentials..."
    
    # Test by actually connecting and running a simple query
    local result
    result=$(ssh "$SSH_MONGO_HOST" "mongosh --quiet -u '$username' -p '$password' --authenticationDatabase admin social --eval \"
try { 
  var c = db.getCollectionNames().length;
  print('SUCCESS: Connected to social, found ' + c + ' collections');
} catch(e) { 
  print('FAILED: ' + e.message); 
}
\"" 2>&1)
    
    if echo "$result" | grep -q "SUCCESS"; then
        log_success "MongoDB connection verified: $result"
        return 0
    else
        log_error "MongoDB connection test failed: $result"
        return 1
    fi
}

test_mysql_connection() {
    local username=$1
    local password=$2
    
    log_info "Testing MySQL connection with new credentials..."
    
    # Test connection via ProxySQL using kubectl
    local result
    result=$(ssh "$SSH_DB_HOST" "KUBECONFIG=/root/.kube/okcs-dev.yaml kubectl exec proxysql-1-0 -n okcs-dev-db -c proxysql -- mysql -u'$username' -p'$password' -h127.0.0.1 -P6033 -N -e 'SELECT \"SUCCESS: \" || @@hostname;'" 2>&1)
    
    if echo "$result" | grep -q "SUCCESS"; then
        log_success "MySQL connection verified: $result"
        return 0
    else
        log_error "MySQL connection test failed: $result"
        return 1
    fi
}

# ============================================================================
# MYSQL FUNCTIONS (via SSH to db server, calling remote script)
# ============================================================================

create_mysql_user() {
    local username=$1
    local role=$2  # rw or ro
    
    log_info "Creating MySQL user via $REMOTE_MYSQL_SCRIPT on $SSH_DB_HOST"
    
    local mysql_role
    if [[ "$role" == "rw" ]]; then
        mysql_role="developer_rw_role"
    else
        mysql_role="developer_ro_role"
    fi
    
    # Call remote script via SSH
    local output
    output=$(ssh "$SSH_DB_HOST" "sudo $REMOTE_MYSQL_SCRIPT -u '$username' -r '$mysql_role'" 2>&1)
    
    echo "$output"
    
    # Extract password from output
    MYSQL_PASSWORD=$(echo "$output" | grep "^Password:" | awk '{print $2}')
    MYSQL_HOST=$(echo "$output" | grep "^IP:" | awk '{print $2}')
    
    if [[ -n "$MYSQL_PASSWORD" ]]; then
        log_success "MySQL user created: $username"
        return 0
    else
        log_error "Failed to create MySQL user or parse password"
        return 1
    fi
}

drop_mysql_user() {
    local username=$1
    
    log_info "Dropping MySQL user: $username from ProxySQL"
    
    # Drop from ProxySQL via kubectl
    ssh "$SSH_DB_HOST" "sudo bash -c 'export KUBECONFIG=/root/.kube/okcs-dev.yaml && kubectl exec proxysql-1-0 -n okcs-dev-db -c proxysql -- mysql -uadmin -palirezaproxysql -S /tmp/proxysql_admin.sock -e \"DELETE FROM mysql_users WHERE username=\\\"$username\\\"; LOAD MYSQL USERS TO RUNTIME; SAVE MYSQL USERS TO DISK;\"'" 2>&1
    
    # Drop from MySQL backend
    ssh "$SSH_DB_HOST" "sudo mysql --login-path=sqlp -e \"DROP USER IF EXISTS '$username'@'%';\"" 2>&1 || true
    
    log_success "MySQL user dropped: $username"
}

# ============================================================================
# CHECK FUNCTIONS
# ============================================================================

check_mongodb_user() {
    local username=$1
    
    local result
    result=$(ssh "$SSH_MONGO_HOST" "mongosh --quiet -u '$MONGO_ADMIN_USER' -p '$MONGO_ADMIN_PASS' --authenticationDatabase admin --eval \"
var u = db.getSiblingDB('admin').getUser('$username');
if(u) { print('EXISTS: ' + u.roles.map(r => r.role + '@' + r.db).join(', ')); }
else { print('NOT_FOUND'); }
\"" 2>&1)
    echo "$result"
}

check_mysql_user() {
    local username=$1
    
    local result
    result=$(ssh "$SSH_DB_HOST" "sudo mysql --login-path=sqlp -N -e \"
SELECT 'EXISTS' FROM mysql.user WHERE User='$username' LIMIT 1;
\"" 2>&1)
    
    if [[ -z "$result" ]]; then
        echo "NOT_FOUND"
    else
        echo "$result"
    fi
}

# ============================================================================
# LIST FUNCTION
# ============================================================================

list_users() {
    echo ""
    echo "=== MongoDB Personal Users ==="
    ssh "$SSH_MONGO_HOST" "mongosh --quiet -u '$MONGO_ADMIN_USER' -p '$MONGO_ADMIN_PASS' --authenticationDatabase admin --eval \"
db.getSiblingDB('admin').getUsers().users
  .filter(u => u.user !== 'admin' && !u.user.includes('pmm'))
  .forEach(u => print(u.user + ' - ' + u.roles.map(r => r.role + '@' + r.db).join(', ')));
\"" 2>&1
    
    echo ""
    echo "=== MySQL Personal Users ==="
    ssh "$SSH_DB_HOST" "sudo mysql --login-path=sqlp -N -e \"
SELECT User FROM mysql.user 
WHERE User NOT IN ('root', 'mysql.sys', 'mysql.session', 'mysql.infoschema', 'proxysql_mon', 'replication_usr', 'binlog_reader_usr')
AND User NOT LIKE '%_usr'
ORDER BY User;
\"" 2>&1 || echo "(Unable to list MySQL users)"
    echo ""
}

# ============================================================================
# SAVE CREDENTIALS FUNCTION
# ============================================================================

save_credentials() {
    local username=$1
    local mongo_password=$2
    local mysql_password=$3
    local role=$4
    
    mkdir -p "$CREDS_DIR"
    local file="${CREDS_DIR}/${username}_okcs_dev.txt"
    
    cat > "$file" << EOF
# OKCS Dev Credentials for: ${username}
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================

## MongoDB
User: ${username}
Password: ${mongo_password}
Databases: ${MONGO_DATABASES[*]}
URI: mongodb://${username}:${mongo_password}@${MONGO_HOST}:${MONGO_PORT}/?authSource=admin

## MySQL (via ProxySQL)
User: ${username}
Password: ${mysql_password}
Host: proxysql-cluster.okcs-dev-db
Port: 3306
Role: $([ "$role" == "rw" ] && echo "developer_rw_role" || echo "developer_ro_role")
EOF
    
    chmod 600 "$file"
    log_success "Credentials saved to: $file"
}

# ============================================================================
# MAIN LOGIC
# ============================================================================

# Parse arguments
USERNAME=""
ROLE=""
TEST_MODE=false
CHECK_MODE=false
DROP_MODE=false
LIST_MODE=false
SAVE_FILE=false

while getopts ":u:r:tcdlfh" opt; do
    case ${opt} in
        u) USERNAME="$OPTARG" ;;
        r) ROLE="$OPTARG" ;;
        t) TEST_MODE=true ;;
        c) CHECK_MODE=true ;;
        d) DROP_MODE=true ;;
        l) LIST_MODE=true ;;
        f) SAVE_FILE=true ;;
        h) usage ;;
        \?) log_error "Invalid option: -$OPTARG"; usage ;;
        :) log_error "Option -$OPTARG requires an argument"; usage ;;
    esac
done

# Handle list mode (no username required)
if [[ "$LIST_MODE" == "true" ]]; then
    list_users
    exit 0
fi

# Validate username for other operations
if [[ -z "$USERNAME" ]]; then
    log_error "Username is required"
    usage
fi

# Handle check mode
if [[ "$CHECK_MODE" == "true" ]]; then
    echo ""
    echo "=== Checking user: $USERNAME ==="
    echo "MongoDB: $(check_mongodb_user "$USERNAME")"
    echo "MySQL:   $(check_mysql_user "$USERNAME")"
    echo ""
    exit 0
fi

# Handle drop mode
if [[ "$DROP_MODE" == "true" ]]; then
    echo ""
    log_warning "This will DROP user: $USERNAME"
    read -p "Are you sure? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Cancelled."
        exit 0
    fi
    
    # Need tunnel for ProxySQL drop
    setup_ssh_tunnel
    
    drop_mongodb_user "$USERNAME"
    drop_mysql_user "$USERNAME"
    exit 0
fi

# Create mode: validate role
if [[ -z "$ROLE" ]] || [[ ! "$ROLE" =~ ^(rw|ro)$ ]]; then
    log_error "Role must be 'rw' or 'ro'"
    usage
fi

# Generate passwords
MONGO_PASSWORD=$(generate_mongo_password "$USERNAME")

echo ""
echo "=============================================="
echo -e "${CYAN}OKCS Dev User Creation v${VERSION}${NC}"
echo "=============================================="
echo "Username: $USERNAME"
echo "Role: $ROLE"
echo "Test mode: $TEST_MODE"
echo "Save to file: $SAVE_FILE"
echo "=============================================="
echo ""

# Step 0: Setup SSH tunnel for Kubernetes API
log_step "0/4" "Setting up SSH tunnel..."
if ! setup_ssh_tunnel; then
    log_error "Failed to setup SSH tunnel. Aborting."
    exit 1
fi
echo ""

# Step 1: Create MongoDB user
log_step "1/5" "Creating MongoDB user..."
create_mongodb_user "$USERNAME" "$MONGO_PASSWORD" "$ROLE"
echo ""

# Step 2: Create MySQL user (via remote script)
log_step "2/5" "Creating MySQL user..."
create_mysql_user "$USERNAME" "$ROLE"
echo ""

# Step 3: Verify users
log_step "3/5" "Verifying users..."
echo ""
echo "--- MongoDB User ---"
verify_mongodb_user "$USERNAME"
echo ""

# Step 4: Test actual connections
log_step "4/5" "Testing connections with new credentials..."
echo ""
test_mongodb_connection "$USERNAME" "$MONGO_PASSWORD"
test_mysql_connection "$USERNAME" "$MYSQL_PASSWORD"
echo ""

# Output final credentials
echo ""
echo "=============================================="
echo -e "${GREEN}USER CREATED SUCCESSFULLY${NC}"
echo "=============================================="
echo ""
echo "=== MongoDB ==="
echo "User: $USERNAME"
echo "Password: $MONGO_PASSWORD"
echo "Databases: ${MONGO_DATABASES[*]}"
echo "URI: mongodb://${USERNAME}:${MONGO_PASSWORD}@${MONGO_HOST}:${MONGO_PORT}/?authSource=admin"
echo ""
echo "=== MySQL ==="
echo "User: $USERNAME"
echo "Password: $MYSQL_PASSWORD"
echo "Host: proxysql-cluster.okcs-dev-db"
echo "Port: 3306"
echo "Role: $([ "$ROLE" == "rw" ] && echo "developer_rw_role" || echo "developer_ro_role")"
echo ""
echo "=============================================="

# Save to file if requested
if [[ "$SAVE_FILE" == "true" ]]; then
    save_credentials "$USERNAME" "$MONGO_PASSWORD" "$MYSQL_PASSWORD" "$ROLE"
fi

# Test mode: cleanup
if [[ "$TEST_MODE" == "true" ]]; then
    echo ""
    log_warning "TEST MODE: Cleaning up user..."
    read -p "Press Enter to drop user $USERNAME or Ctrl+C to cancel..."
    
    drop_mongodb_user "$USERNAME"
    drop_mysql_user "$USERNAME"
    
    log_success "Test user $USERNAME has been dropped"
fi

# Step 5: Cleanup (trap will handle tunnel cleanup)
log_step "5/5" "Cleanup..."
log_success "Done!"
