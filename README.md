***

### English

> **backup.py - BorgBackup automation tool**

Automates full-system backups and restores for Linux using **BorgBackup**.  
Supports Docker service control, MySQL/PostgreSQL dumps, system package and service state saving, live progress display, and full system recovery with reconfiguration.

***

#### Features
- Full or partial system backup with BorgBackup  
- MySQL and PostgreSQL database dumps  
- Docker stop/start during backup  
- Package, service, and cron state preservation  
- Interactive archive listing and restore  
- Live progress display in terminal  
- Automatic dependency installation  

***

#### Requirements
- **Python 3.8+**  
- **BorgBackup**, **parted**, **e2fsprogs**, **dosfstools**

***

#### Installation
```bash
sudo apt install python3 borgbackup
chmod +x backup.py
sudo mv backup.py /usr/local/bin/backup.py
```

***

#### Usage
```bash
# Full system backup
backup.py --repo user@host:/path/repo --key ~/.ssh/id_rsa --backup --all

# Restore system
backup.py --repo user@host:/path/repo --key ~/.ssh/id_rsa --restore --all

# List existing archives
backup.py --repo user@host:/path/repo --list

# Delete all archives
backup.py --repo user@host:/path/repo --clear-all
```

Logs and state data are stored in `/root/.backup.py`.

***

#### Tags
`python` `backup` `borgbackup` `linux` `automation` `docker` `postgresql` `mysql` `devops` `system-backup`

***

### Русский

> **backup.py - инструмент автоматизации BorgBackup**

Автоматизирует полное резервное копирование и восстановление Linux‑систем с помощью **BorgBackup**.  
Поддерживает управление Docker, дампы MySQL/PostgreSQL, сохранение списка пакетов, сервисов и заданий cron, отображение прогресса и восстановление состояния системы.

***

#### Возможности
- Полное или частичное резервное копирование  
- Создание SQL‑дампов MySQL и PostgreSQL  
- Остановка/запуск Docker во время бэкапа  
- Сохранение и восстановление состояния пакетов и сервисов  
- Просмотр и выбор архива для восстановления  
- Отображение прогресса в терминале  
- Автоматическая установка зависимостей  

***

#### Требования
- **Python 3.8+**  
- **BorgBackup**, **parted**, **e2fsprogs**, **dosfstools**

***

#### Установка
```bash
sudo apt install python3 borgbackup
chmod +x backup.py
sudo mv backup.py /usr/local/bin/backup.py
```

***

#### Использование
```bash
# Полный бэкап системы
backup.py --repo user@host:/path/repo --key ~/.ssh/id_rsa --backup --all

# Восстановление системы
backup.py --repo user@host:/path/repo --key ~/.ssh/id_rsa --restore --all

# Список архивов
backup.py --repo user@host:/path/repo --list

# Удаление всех архивов
backup.py --repo user@host:/path/repo --clear-all
```

Логи и состояние системы сохраняются в `/root/.backup.py`.

***

Хочешь, чтобы я добавил раздел с примером расписания (cron) для автоматического запуска резервного копирования?
