#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "❌ This script must be run as root (sudo ./install.sh)" >&2
  exit 1
fi

echo "=== backup.py installer (root mode) ==="

# Выбор часа запуска
echo "Backup time (24h format, default 03:00):"
echo "  1) 02:00   2) 03:00   3) 04:00   4) Custom"
read -rp "> " hour_choice
case "$hour_choice" in
  1) hour="2" ;;
  2) hour="3" ;; 
  3) hour="4" ;;
  4) read -rp "Enter hour (0-23): " hour ;;
  *) hour="3" ;;
esac

# 1) Как часто запускать бэкап в неделю
echo "How many times per week? (1-7, default 1)"
echo "  1) Daily    2) 6x/week  3) 5x/week  4) 4x/week  5) 3x/week  6) 2x/week  7) Weekly"
read -r runs_per_week
runs_per_week=${runs_per_week:-1}

case "$runs_per_week" in
  1) cron_day="0-6" ;;      # daily
  2) cron_day="1-6" ;;      # Mon-Sat  
  3) cron_day="1-5" ;;      # Mon-Fri
  4) cron_day="1-4" ;;      # Mon-Thu
  5) cron_day="1,3,5" ;;    # Mon,Wed,Fri
  6) cron_day="1,4" ;;      # Mon,Thu
  7) cron_day="1" ;;        # Monday
  *) cron_day="1" ;;        # default weekly
esac

cron_time="$hour 0 * * $cron_day"  # minute=0, hour, day-of-month=*, month=*, day-of-week

# 2) Borg passphrase
read -rsp $'\n🔐 Enter Borg passphrase: ' borg_pass
echo

# 3) SSH URL репозитория
read -rp $'\n📁 Borg repo (ssh://user@host:/path/repo): ' borg_repo

# 4) Каталог для бэкапа
read -rp $'\n📂 Backup target [/]: ' backup_target
backup_target=${backup_target:-/}

# 5) SSH ключ
read -rp $'\n🔑 SSH key [~/.ssh/id_rsa]: ' ssh_key
ssh_key=${ssh_key:-~/.ssh/id_rsa}
ssh_key=$(eval echo "$ssh_key")  # expand ~/

# Проверка backup.py
if ! command -v backup.py >/dev/null 2>&1; then
  echo "❌ backup.py not found in PATH. Installing dependencies..."
  apt update
  apt install -y python3 borgbackup parted dosfstools e2fsprogs
  echo "⚠️  Please install backup.py manually (e.g. chmod +x backup.py; mv backup.py /usr/local/bin/)"
  exit 1
fi

# 6) Создание crontab записи
log_file="/var/log/backup.py.log"
cron_cmd="BORG_PASSPHRASE='$borg_pass' backup.py --repo '$borg_repo' --key '$ssh_key' --target '$backup_target' --backup --all >> $log_file 2>&1"

cron_line="$cron_time $cron_cmd"

# Удаляем старые записи и добавляем новую
(crontab -l 2>/dev/null | grep -Fv "backup.py --repo '$borg_repo'" || true; echo "$cron_line") | crontab -

# Создаём лог файл
touch "$log_file"
chmod 644 "$log_file"

echo "✅ Installed!"
echo ""
echo "📅 Cron job:"
echo "   $cron_line"
echo ""
echo "📋 Verify: crontab -l"
echo "📊 Logs:   tail -f $log_file"
echo ""
echo "Next backup: $(date -d "$hour:00 tomorrow" '+%Y-%m-%d %H:%M')"
