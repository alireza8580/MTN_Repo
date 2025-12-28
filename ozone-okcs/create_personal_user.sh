#!/bin/bash
# ============================================================================
# OKCS Personal User Creation Script
# Creates both MongoDB and MySQL users for individual developers
# 
# Usage: 
#   ./create_personal_user.sh -u <username> -r <rw|ro> [-e <dev|prod>] [-t]
#
# Examples:
#   ./create_personal_user.sh -u e_alinaqizadeh -r rw           # Dev RW
#   ./create_personal_user.sh -u e_alinaqizadeh -r ro -e prod   # Prod RO
#   ./create_personal_user.sh -u a_gheshlaghi_test -r rw -t     # Test mode (cleanup after)
#
# Author: Alireza Aghajanzadeh Gheshlaghi
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# CONFIGURATION
# ============================================================================

# MongoDB databases for OKCS
MONGO_DATABASES=("third_party_proxy" "ozone_card_proxy")

# MySQL authentication plugin
MYSQL_AUTH_PLUGIN="mysql_native_password"

# Connection limits for individual users
MAX_CONNECTIONS_PER_HOUR=180
MAX_QUERIES_PER_HOUR=2000
FAILED_LOGIN_ATTEMPTS=30
PASSWORD_LOCK_TIME=1
MAX_PROXYSQL_CONNECTIONS=50

# ProxySQL admin credentials
PROXYSQL_ADMIN_USER="admin"
PROXYSQL_ADMIN_PASS_DEV="alirezaproxysql"
PROXYSQL_ADMIN_PASS_PROD="alirezaproxysqls"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 -u <username> -r <rw|ro> [-e <dev|prod>] [-t]

Options:
  -u username   Required. Username in format: f_lastname (e.g., e_alinaqizadeh)
  -r role       Required. Access level: 'rw' (read-write) or 'ro' (read-only)
  -e env        Optional. Environment: 'dev' (default) or 'prod'
  -t            Optional. Test mode - creates user and then drops it
  -h            Show this help message

Examples:
  $0 -u e_alinaqizadeh -r rw              # Create RW user in dev
  $0 -u e_alinaqizadeh -r ro -e prod      # Create RO user in prod
  $0 -u test_user -r rw -t                # Test mode (create and drop)

EOF
    exit 1
}

generate_password() {
    local username=$1
    local env=$2
    local year=$(date +%Y)
    # Format: username_okcs_env_year
    echo "${username}_okcs_${env}_${year}"
}

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

setup_environment() {
    local env=$1
    
    if [[ "$env" == "dev" ]]; then
        export KUBECONFIG=/root/.kube/okcs-dev.yaml
        PROXYSQL_HOST="proxysql-cluster.okcs-dev-db"
        PROXYSQL_NAMESPACE="okcs-dev-db"
        PROXYSQL_POD="proxysql-1-0"
        PROXYSQL_ADMIN_PASS="$PROXYSQL_ADMIN_PASS_DEV"
        MONGO_HOST="okcs-dev-mongo1.local"
        MONGO_PORT="27017"
        MONGO_ADMIN_USER="admin"
        MONGO_ADMIN_PASS="ozone_okcs_dev_mongo_2024"
        MONGO_REPLICA_SET="ozone_okcs_dev_rs"
        MYSQL_PREFIX="%"
        MYSQL_LOGIN_PATH="sqlp"
        # Hostgroup: 100 = writer, 101 = reader
        MYSQL_HOSTGROUP_RW=100
        MYSQL_HOSTGROUP_RO=101
        MYSQL_ROLE_RW="developer_rw_role"
        MYSQL_ROLE_RO="developer_ro_role"
    elif [[ "$env" == "prod" ]]; then
        export KUBECONFIG=/root/.kube/okcs-prd.yaml
        PROXYSQL_HOST="proxysql-cluster.okcs-prod-db"
        PROXYSQL_NAMESPACE="okcs-prod-db"
        PROXYSQL_POD="proxysql-1-0"
        PROXYSQL_ADMIN_PASS="$PROXYSQL_ADMIN_PASS_PROD"
        MONGO_HOST="okcs-prd-mongo1.local"
        MONGO_PORT="27017"
        MONGO_ADMIN_USER="admin"
        MONGO_ADMIN_PASS="ozone_okcs_prod_mongo_2024"
        MONGO_REPLICA_SET="ozone_okcs_prod_rs"
        MYSQL_PREFIX="87.247.185.186"
        MYSQL_LOGIN_PATH="rep"
        MYSQL_HOSTGROUP_RW=100
        MYSQL_HOSTGROUP_RO=101
        MYSQL_ROLE_RW="developer_rw_role"
        MYSQL_ROLE_RO="developer_ro_role"
    else
        log_error "Unknown environment: $env"
        exit 1
    fi
    
    ENV="$env"
    log_info "Environment set to: ${ENV^^}"
}

# ============================================================================
# MONGODB FUNCTIONS
# ============================================================================

create_mongodb_user() {
    local username=$1
    local password=$2
    local role=$3  # rw or ro
    
    log_info "Creating MongoDB user: $username"
    
    # Determine MongoDB role
    local mongo_role
    if [[ "$role" == "rw" ]]; then
        mongo_role="readWrite"
    else
        mongo_role="read"
    fi
    
    # Build roles array for all databases
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
    
    # Create user via mongosh
    mongosh --host "$MONGO_HOST" --port "$MONGO_PORT" \
        -u "$MONGO_ADMIN_USER" -p "$MONGO_ADMIN_PASS" \
        --authenticationDatabase admin --quiet << EOF
db = db.getSiblingDB("admin");

// Drop user if exists (for idempotency)
try {
    db.dropUser("$username");
    print("Dropped existing user: $username");
} catch (e) {
    print("User does not exist, creating new: $username");
}

// Create user with roles
db.createUser({
    user: "$username",
    pwd: "$password",
    roles: $roles_json
});

print("Created MongoDB user: $username with role: $mongo_role");
EOF

    if [[ $? -eq 0 ]]; then
        log_success "MongoDB user created: $username"
        return 0
    else
        log_error "Failed to create MongoDB user: $username"
        return 1
    fi
}

drop_mongodb_user() {
    local username=$1
    
    log_info "Dropping MongoDB user: $username"
    
    mongosh --host "$MONGO_HOST" --port "$MONGO_PORT" \
        -u "$MONGO_ADMIN_USER" -p "$MONGO_ADMIN_PASS" \
        --authenticationDatabase admin --quiet << EOF
db = db.getSiblingDB("admin");
try {
    db.dropUser("$username");
    print("Dropped MongoDB user: $username");
} catch (e) {
    print("User does not exist: $username");
}
EOF
    
    log_success "MongoDB user dropped: $username"
}

verify_mongodb_user() {
    local username=$1
    
    log_info "Verifying MongoDB user: $username"
    
    mongosh --host "$MONGO_HOST" --port "$MONGO_PORT" \
        -u "$MONGO_ADMIN_USER" -p "$MONGO_ADMIN_PASS" \
        --authenticationDatabase admin --quiet --eval "
            var user = db.getSiblingDB('admin').getUser('$username');
            if (user) {
                print('User found: ' + user.user);
                print('Roles: ' + JSON.stringify(user.roles));
            } else {
                print('User NOT found');
            }
        "
}

# ============================================================================
# MYSQL FUNCTIONS
# ============================================================================

create_mysql_user() {
    local username=$1
    local password=$2
    local role=$3  # rw or ro
    
    log_info "Creating MySQL user: $username"
    
    # Determine MySQL role
    local mysql_role
    local hostgroup
    if [[ "$role" == "rw" ]]; then
        mysql_role="$MYSQL_ROLE_RW"
        hostgroup=$MYSQL_HOSTGROUP_RW
    else
        mysql_role="$MYSQL_ROLE_RO"
        hostgroup=$MYSQL_HOSTGROUP_RO
    fi
    
    # Create user in MySQL via login-path
    mysql --login-path="$MYSQL_LOGIN_PATH" -N << EOF
-- Drop user if exists for idempotency
DROP USER IF EXISTS '$username'@'$MYSQL_PREFIX';

-- Create user with role
CREATE USER '$username'@'$MYSQL_PREFIX' 
    IDENTIFIED WITH $MYSQL_AUTH_PLUGIN BY '$password'
    DEFAULT ROLE '$mysql_role'
    WITH MAX_QUERIES_PER_HOUR $MAX_QUERIES_PER_HOUR 
    MAX_CONNECTIONS_PER_HOUR $MAX_CONNECTIONS_PER_HOUR 
    FAILED_LOGIN_ATTEMPTS $FAILED_LOGIN_ATTEMPTS 
    PASSWORD_LOCK_TIME $PASSWORD_LOCK_TIME;

SELECT 'MySQL user created successfully' AS status;
EOF

    if [[ $? -ne 0 ]]; then
        log_error "Failed to create MySQL user: $username"
        return 1
    fi
    
    log_success "MySQL user created: $username"
    
    # Get authentication string for ProxySQL
    local auth_string
    auth_string=$(mysql --login-path="$MYSQL_LOGIN_PATH" -N -B -e \
        "SELECT authentication_string FROM mysql.user WHERE user='$username' AND host='$MYSQL_PREFIX'")
    
    if [[ -z "$auth_string" ]]; then
        log_error "Could not get auth string for user: $username"
        return 1
    fi
    
    # Add user to ProxySQL
    log_info "Adding user to ProxySQL..."
    
    kubectl exec "$PROXYSQL_POD" -n "$PROXYSQL_NAMESPACE" -c proxysql -- \
        mysql -u"$PROXYSQL_ADMIN_USER" -p"$PROXYSQL_ADMIN_PASS" -S /tmp/proxysql_admin.sock -N -e "
            DELETE FROM mysql_users WHERE username='$username';
            INSERT INTO mysql_users (username, password, active, default_hostgroup, max_connections) 
                VALUES ('$username', '$auth_string', 1, $hostgroup, $MAX_PROXYSQL_CONNECTIONS);
            LOAD MYSQL USERS TO RUNTIME;
            SAVE MYSQL USERS TO DISK;
            SELECT 'ProxySQL user added' AS status;
        "
    
    if [[ $? -eq 0 ]]; then
        log_success "ProxySQL user added: $username"
        return 0
    else
        log_error "Failed to add ProxySQL user: $username"
        return 1
    fi
}

drop_mysql_user() {
    local username=$1
    
    log_info "Dropping MySQL user: $username"
    
    # Drop from MySQL
    mysql --login-path="$MYSQL_LOGIN_PATH" -N -e \
        "DROP USER IF EXISTS '$username'@'$MYSQL_PREFIX';"
    
    # Drop from ProxySQL
    kubectl exec "$PROXYSQL_POD" -n "$PROXYSQL_NAMESPACE" -c proxysql -- \
        mysql -u"$PROXYSQL_ADMIN_USER" -p"$PROXYSQL_ADMIN_PASS" -S /tmp/proxysql_admin.sock -N -e "
            DELETE FROM mysql_users WHERE username='$username';
            LOAD MYSQL USERS TO RUNTIME;
            SAVE MYSQL USERS TO DISK;
        " 2>/dev/null
    
    log_success "MySQL user dropped: $username"
}

verify_mysql_user() {
    local username=$1
    
    log_info "Verifying MySQL user: $username"
    
    mysql --login-path="$MYSQL_LOGIN_PATH" -e \
        "SELECT user, host, default_role FROM mysql.user WHERE user='$username';"
    
    log_info "Verifying ProxySQL user: $username"
    
    kubectl exec "$PROXYSQL_POD" -n "$PROXYSQL_NAMESPACE" -c proxysql -- \
        mysql -u"$PROXYSQL_ADMIN_USER" -p"$PROXYSQL_ADMIN_PASS" -S /tmp/proxysql_admin.sock -N -e \
        "SELECT username, default_hostgroup, max_connections FROM mysql_users WHERE username='$username';"
}

# ============================================================================
# OUTPUT FUNCTIONS
# ============================================================================

print_credentials() {
    local username=$1
    local password=$2
    local role=$3
    local env=$4
    
    echo ""
    echo "============================================================================"
    echo -e "${GREEN}User Created Successfully!${NC}"
    echo "============================================================================"
    echo ""
    echo "=== MongoDB Credentials ==="
    echo "Username: $username"
    echo "Password: $password"
    echo ""
    echo "MongoDB URIs:"
    for db in "${MONGO_DATABASES[@]}"; do
        echo "  $db:"
        echo "    mongodb://$username:$password@$MONGO_HOST:$MONGO_PORT/$db?replicaSet=$MONGO_REPLICA_SET&authSource=admin"
    done
    echo ""
    echo "=== MySQL Credentials ==="
    echo "Username: $username"
    echo "Password: $password"
    echo "Host: $PROXYSQL_HOST"
    echo "Port: 3306"
    echo "Role: $([ "$role" == "rw" ] && echo "$MYSQL_ROLE_RW" || echo "$MYSQL_ROLE_RO")"
    echo ""
    echo "MySQL Connection:"
    echo "  mysql -u$username -p'$password' -h $PROXYSQL_HOST -P 3306"
    echo ""
    echo "============================================================================"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    local username=""
    local role=""
    local env="dev"
    local test_mode=false
    
    # Parse arguments
    while getopts ":u:r:e:th" opt; do
        case "${opt}" in
            u) username="${OPTARG}" ;;
            r) role="${OPTARG}" ;;
            e) env="${OPTARG}" ;;
            t) test_mode=true ;;
            h) usage ;;
            *) usage ;;
        esac
    done
    
    # Validate required arguments
    if [[ -z "$username" ]]; then
        log_error "Username is required"
        usage
    fi
    
    if [[ -z "$role" ]]; then
        log_error "Role is required"
        usage
    fi
    
    if [[ "$role" != "rw" && "$role" != "ro" ]]; then
        log_error "Role must be 'rw' or 'ro'"
        usage
    fi
    
    if [[ "$env" != "dev" && "$env" != "prod" ]]; then
        log_error "Environment must be 'dev' or 'prod'"
        usage
    fi
    
    # Setup environment
    setup_environment "$env"
    
    # Generate password
    local password
    password=$(generate_password "$username" "$env")
    
    echo ""
    log_info "Creating personal user: $username"
    log_info "Environment: ${env^^}"
    log_info "Role: $role"
    log_info "Password: $password"
    echo ""
    
    # Create MongoDB user
    if ! create_mongodb_user "$username" "$password" "$role"; then
        log_error "MongoDB user creation failed"
        exit 1
    fi
    
    # Create MySQL user
    if ! create_mysql_user "$username" "$password" "$role"; then
        log_error "MySQL user creation failed"
        # Rollback MongoDB user
        drop_mongodb_user "$username"
        exit 1
    fi
    
    # Verify users
    echo ""
    log_info "=== Verification ==="
    verify_mongodb_user "$username"
    verify_mysql_user "$username"
    
    # Print credentials
    print_credentials "$username" "$password" "$role" "$env"
    
    # Test mode - cleanup
    if [[ "$test_mode" == "true" ]]; then
        echo ""
        log_warning "Test mode enabled - cleaning up..."
        drop_mongodb_user "$username"
        drop_mysql_user "$username"
        log_success "Test cleanup completed"
    fi
}

# Run main function
main "$@"
