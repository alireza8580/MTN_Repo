# .bashrc

# Source global definitions
if [ -f /etc/bashrc ]; then
        . /etc/bashrc
fi

# Uncomment the following line if you don't like systemctl's auto-paging feature:
# export SYSTEMD_PAGER=

# User specific aliases and functions
shopt -s direxpand
LOCK_DIR="/oracle/alireza/script/lock_account_dir"
alias cdlock="cd ${LOCK_DIR}"
function lockacc() {
  local username
  for username in "$@"; do
    echo "============================================"
    echo "🔒 Locking user: $username"
    echo "============================================"
    "${LOCK_DIR}/lock_account.sh" "$username"
    echo ""
    sleep 4s
  done
}

function lockacc() {
  if [ "$#" -eq 0 ]; then
    echo "❗ Usage: lockacc <firstname.lastname> [firstname.lastname2] [...]"
    sleep 2s
    return 1
  fi

  local username
  local success=0
  local failure=0

  for username in "$@"; do
    # Validate format: at least 2 chars before dot, at least 1 after
    if [[ ! "$username" =~ ^[a-zA-Z0-9._-]{2,}\.[a-zA-Z0-9_-]+$ ]]; then
      echo "🚫 Invalid username format: '$username'. Must be  valid ldap user for example: alireza.aghaja"
      failure=$((failure+1))
      sleep 5s
      continue
    fi

    echo "============================================"
    echo "🔒 Locking user: $username"
    echo "============================================"
    "${LOCK_DIR}/lock_account.sh" "$username"
    if [ $? -ne 0 ]; then
      echo "❌ Failed texecution for user:$username"
      failure=$((failure+1))
    else
      echo "✅ Successfull execution for user: $username"
      success=$((success+1))
    fi
    echo ""
  done

  echo "🎯 Summary: $success success, $failure failed."
}
