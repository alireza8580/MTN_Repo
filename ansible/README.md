# MTN MySQL 8.4 Ansible Automation

This directory contains Ansible automation for MySQL 8.4 Enterprise Edition installation and configuration for MTN IranCell.

## Directory Structure

```
ansible/
├── ansible.cfg                 # Ansible configuration
├── playbooks/
│   └── install_mysql.yml       # Main installation playbook
├── inventory/
│   └── mtn_mysql/
│       ├── hosts.yml           # Host inventory template
│       └── group_vars/
│           └── mysql_servers.yml
└── roles/
    └── mysql_install/
        ├── defaults/main.yml   # Default variables
        ├── handlers/main.yml   # Handlers
        ├── meta/main.yml       # Role metadata
        ├── tasks/
        │   ├── main.yml        # Task orchestration
        │   ├── prerequisites.yml
        │   ├── disk_setup.yml
        │   ├── directories.yml
        │   ├── packages.yml
        │   ├── configure.yml
        │   ├── service.yml
        │   ├── secure_installation.yml
        │   ├── cis_hardening.yml
        │   ├── users.yml
        │   ├── shell_config.yml
        │   └── backup.yml
        └── templates/
            ├── my.cnf.j2
            ├── bash_profile.j2
            └── backup_script.sh.j2
```

## Prerequisites

Before running the playbook, ensure UNIX team has:

1. Installed MySQL RPMs from `/net/dru112c/dba_data/dba-tools/mysql/8.4/el8/*.rpm`
2. Mounted NFS for backups (dru112c:/db-bkp or equivalent)
3. Set limits for mysql user:
   - open files: 32000
   - max user processes: 41000
4. Configured mailx
5. Granted crontab permission to mysql user
6. Set `/data` as home folder for mysql user
7. Granted sudo access for:
   - systemctl commands for mysqld
   - CIS Assessor
   - Plugin directory permissions

## Quick Start

### 1. Configure Inventory

Copy and edit the inventory file:

```bash
cp inventory/mtn_mysql/hosts.yml inventory/mtn_mysql/production.yml
```

Edit `production.yml`:
```yaml
mysql_servers:
  hosts:
    t3vl717:
      ansible_host: 10.x.x.x
      mysql_server_id: 717
      is_master: true
```

### 2. Set Password (Use Ansible Vault!)

```bash
# Create vault file
ansible-vault create inventory/mtn_mysql/vault.yml
```

Add to vault:
```yaml
mysql_root_password: "R0L3#dbAhs_2021"
```

### 3. Run Installation

```bash
# Full installation
ansible-playbook playbooks/install_mysql.yml \
  -i inventory/mtn_mysql/production.yml \
  --ask-vault-pass

# Dry run first
ansible-playbook playbooks/install_mysql.yml \
  -i inventory/mtn_mysql/production.yml \
  --check
```

## Available Tags

| Tag | Description |
|-----|-------------|
| `mysql_install` | Full installation |
| `mysql_install:prerequisites` | Check system prerequisites |
| `mysql_install:disk` | Disk/LVM setup |
| `mysql_install:directories` | Create directories |
| `mysql_install:packages` | Install MySQL RPMs |
| `mysql_install:configure` | Deploy my.cnf |
| `mysql_install:service` | Service management |
| `mysql_install:secure` | Secure installation |
| `mysql_install:cis` | CIS hardening |
| `mysql_install:users` | User setup |
| `mysql_install:shell` | Shell configuration |
| `mysql_install:backup` | Backup setup (backup nodes only) |

### Examples

```bash
# Skip disk setup (already done)
ansible-playbook playbooks/install_mysql.yml -i inventory/mtn_mysql/hosts.yml \
  --skip-tags mysql_install:disk

# Only apply CIS hardening
ansible-playbook playbooks/install_mysql.yml -i inventory/mtn_mysql/hosts.yml \
  --tags mysql_install:cis

# Only configure backup
ansible-playbook playbooks/install_mysql.yml -i inventory/mtn_mysql/hosts.yml \
  --tags mysql_install:backup
```

## CIS Hardening

The role implements these CIS MySQL 8.4 Benchmark controls:

| CIS Rule | Description | Implementation |
|----------|-------------|----------------|
| 3.1 | Data directory permissions | chmod 750 |
| 3.2 | Binary log permissions | chmod 660 |
| 3.3 | Error log permissions | chmod 600 |
| 3.4 | Slow query log permissions | chmod 660 |
| 3.8 | Plugin directory | chmod 550, mysql:mysql |
| 3.9 | Audit log permissions | chmod 660 |
| 2.7/7.4 | Password lifetime | 365 days |
| 2.8 | Password history | 5 passwords, 365 days |

## Post-Installation

After successful installation:

1. **Login to MySQL:**
   ```bash
   mysql --login-path=sqlp6
   ```

2. **Check service status:**
   ```bash
   sudo systemctl status mysqld@3306
   ```

3. **Run CIS Assessment:**
   ```bash
   sudo /data/cis/Assessor/Assessor-CLI.sh \
     -b /data/cis/Assessor/benchmarks/CIS_Oracle_MySQL_Enterprise_Edition_8.4_Benchmark_v1.0.0-xccdf.xml
   ```

## Troubleshooting

### Common Issues

1. **Disk device not found:**
   - Verify device exists: `ls -la /dev/sdb`
   - Skip disk setup if already configured: `--skip-tags mysql_install:disk`

2. **MySQL RPMs not accessible:**
   - Verify NFS mount: `ls /net/dru112c/dba_data/dba-tools/mysql/8.4/el8/`
   - Request UNIX team to mount NFS

3. **Permission denied for plugin directory:**
   - This requires sudo - ensure UNIX team has granted access
   - Run: `sudo chmod 550 /usr/lib64/mysql/plugin`

4. **CIS 3.9 audit_log fails:**
   - This may be a CIS-CAT tool bug (wrong path)
   - Verify manually: `ls -la /data/3306/audit/audit.log`

## Reference

- [CIS MySQL 8.4 Benchmark](https://www.cisecurity.org/benchmark/mysql)
- [MySQL 8.4 Documentation](https://dev.mysql.com/doc/refman/8.4/en/)
- [Manual Installation Guide](../mysql_installation_manual_8.4_20251130_enhanced.txt)
