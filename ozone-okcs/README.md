# OKCS Dev User Management Scripts

Scripts for managing personal developer access to MongoDB and MySQL databases on the Ozone-OKCS development environment.

## Overview

These tools create user accounts in:
- **MongoDB**: social, third_party_proxy databases
- **MySQL**: Accessed through ProxySQL in Kubernetes

## Quick Start

### Using Bash Script (Recommended)

```bash
cd /root/infrastructure/scripts/ozone-okcs

# Create a read-write user
./create_okcs_dev_user.sh -u f_lastname -r rw

# Create a read-only user
./create_okcs_dev_user.sh -u f_lastname -r ro
```

### Using Ansible Playbook

```bash
cd /root/infrastructure

# Create a read-write user
ansible-playbook playbooks/ozone-okcs/create_personal_user.yml \
  -e "username=f_lastname role=rw"
```

## Bash Script Options

| Flag | Description | Example |
|------|-------------|---------|
| `-u username` | Username (format: f_lastname) | `-u e_alinaqizadeh` |
| `-r rw\|ro` | Role: read-write or read-only | `-r rw` |
| `-c` | Check if user exists | `-u e_alinaqizadeh -c` |
| `-d` | Drop/delete user (with confirmation) | `-u old_user -d` |
| `-l` | List all personal users | `-l` |
| `-f` | Save credentials to file | `-u e_alinaqizadeh -r rw -f` |
| `-t` | Test mode (create then drop) | `-u test_user -r rw -t` |
| `-h` | Show help | `-h` |

## Usage Examples

### Create User and Save Credentials

```bash
./create_okcs_dev_user.sh -u e_alinaqizadeh -r rw -f

# Credentials saved to: ~/.okcs_credentials/e_alinaqizadeh_okcs_dev.txt
```

### Check If User Exists

```bash
./create_okcs_dev_user.sh -u e_alinaqizadeh -c

# Output:
# === Checking user: e_alinaqizadeh ===
# MongoDB: EXISTS: readWrite@social, readWrite@third_party_proxy
# MySQL:   EXISTS
```

### List All Personal Users

```bash
./create_okcs_dev_user.sh -l

# Output:
# === MongoDB Personal Users ===
# ar_sabzian - readWrite@ozone_card_proxy, readWrite@third_party_proxy
# e_alinaqizadeh - readWrite@third_party_proxy, readWrite@social
# ...
#
# === MySQL Personal Users ===
# a_gheshlaghi
# e_alinaqizadeh
# ...
```

### Drop User

```bash
./create_okcs_dev_user.sh -u old_user -d

# Prompts: "This will DROP user: old_user. Are you sure? (y/N):"
```

### Test Mode (Development)

```bash
./create_okcs_dev_user.sh -u test_user -r rw -t

# Creates user, verifies connections, then drops user
```

## Output Format

After successful creation:

```
=== MongoDB ===
User: e_alinaqizadeh
Password: e_alinaqizadeh_okcs_dev_2025
Databases: social third_party_proxy
URI: mongodb://e_alinaqizadeh:e_alinaqizadeh_okcs_dev_2025@okcs-dev-mongo.local:27017/?authSource=admin

=== MySQL ===
User: e_alinaqizadeh
Password: ev/V4omKk3b/oPWZ_Al1
Host: proxysql-cluster.okcs-dev-db
Port: 3306
Role: developer_rw_role
```

## Roles

### MongoDB Roles

| Role | Access Level | Databases |
|------|-------------|-----------|
| `readWrite` | Full read/write | social, third_party_proxy |
| `read` | Read-only | social, third_party_proxy |

### MySQL Roles

| Role | Access Level |
|------|-------------|
| `developer_rw_role` | Read-write access to all dev databases |
| `developer_ro_role` | Read-only access to all dev databases |

## Architecture

```
┌─────────────────────┐
│  Local Machine      │
│     (gheshi)        │
└──────────┬──────────┘
           │ SSH reverse tunnel
           │ -R 16443:172.21.80.175:443
           ▼
┌─────────────────────┐        ┌─────────────────────┐
│  oz-okcs-dev-db1    │───────▶│  Kubernetes API     │
│                     │        │  (172.21.80.175)    │
│  KUBECONFIG uses    │        └─────────────────────┘
│  localhost:16443    │                    │
└──────────┬──────────┘                    ▼
           │                    ┌─────────────────────┐
           │ kubectl exec      │  ProxySQL Pods      │
           └───────────────────▶│  (proxysql-1-0)     │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  MySQL Backend      │
                               └─────────────────────┘

                               ┌─────────────────────┐
                               │  MongoDB            │
   oz-okcs-dev-mongo1 ────────▶│  (192.168.121.63)   │
                               └─────────────────────┘
```

## Verification Steps

The script performs these verification steps:

1. **SSH Tunnel**: Verifies Kubernetes API is accessible via tunnel
2. **User Creation**: Confirms MongoDB and MySQL users were created
3. **Connection Test**: Actually connects with new credentials to verify they work
   - MongoDB: Lists collections in social database
   - MySQL: Executes SELECT @@hostname query

## Files

| File | Purpose |
|------|---------|
| `create_okcs_dev_user.sh` | Main bash script (run from local machine) |
| `~/.okcs_credentials/` | Directory for saved credentials (with -f flag) |
| `/opt/db_scripts/create_user_kuber.sh` | Remote script on oz-okcs-dev-db1 for MySQL user creation |

## Related Ansible Playbook

Location: `playbooks/ozone-okcs/create_personal_user.yml`

```bash
# Create user
ansible-playbook playbooks/ozone-okcs/create_personal_user.yml \
  -e "username=f_lastname role=rw"

# Test mode
ansible-playbook playbooks/ozone-okcs/create_personal_user.yml \
  -e "username=test_user role=rw test_mode=true"
```

## Requirements

- SSH access to oz-okcs-dev-db1 and oz-okcs-dev-mongo1
- Network path from local machine to 172.21.80.175:443 (Kubernetes API)
- `mongosh` client on oz-okcs-dev-mongo1
- `kubectl` and proper KUBECONFIG on oz-okcs-dev-db1

## Troubleshooting

### SSH Tunnel Fails

```bash
# Check if port is in use
ssh oz-okcs-dev-db1 "sudo fuser 16443/tcp"

# Kill existing tunnel
pkill -f "R 16443:172.21.80.175:443"
```

### MongoDB Connection Timeout

The script has built-in retry logic. If MongoDB is unreachable:
1. Verify oz-okcs-dev-mongo1 is accessible via SSH
2. Check MongoDB is running: `ssh oz-okcs-dev-mongo1 "systemctl status mongod"`

### MySQL User Not Created

Check the remote script:
```bash
ssh oz-okcs-dev-db1 "sudo /opt/db_scripts/create_user_kuber.sh -h"
```

## Author

Alireza Aghajanzadeh Gheshlaghi
