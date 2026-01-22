#!/usr/bin/env python3
# backup.py v4.8 - Clean, stable, Python 3.8+

import argparse
import getpass
import logging
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from shutil import which

REQUIRED_PKGS = ["borgbackup", "parted", "dosfstools", "e2fsprogs"]
BASE_EXCLUDES = [
    "/dev/**", "/proc/**", "/sys/**", "/run/**", "/tmp/**",
    "/mnt/**", "/media/**", "/lost+found",
    "/var/cache/apt/archives/**",
    "/swapfile", "/swap.img"
]
IDENTITY_EXCLUDES = [
    "/etc/machine-id", "/var/lib/dbus/machine-id",
    "/etc/hostname", "/etc/hosts", "/etc/fstab",
    "/etc/ssh/ssh_host_*", "/etc/netplan/**",
    "/etc/network/interfaces*",
    "/etc/udev/rules.d/70-persistent-net.rules",
    "/var/tmp/systemd-private-*/**", "/tmp/systemd-private-*/**",
    "**/*.log", "/var/log/**", "/var/tmp/*.log",
    "/var/log/journal/**", "/run/log/**",
    "/var/cache/**", "/tmp/**",
    "**/__pycache__/**", "**/.cache/**",
    "**/*.pid", "**/*.sock",
    "/run/**",
    "/var/lib/dpkg/lock*",
    "/var/lib/apt/lists/lock"
]
DEFAULT_RESTORE_EXCLUDES = [
    "etc/machine-id",
    "var/lib/dbus/machine-id",
    "etc/fstab",
    "etc/ssh/ssh_host_*",
    "etc/hostname",
    "etc/netplan"
]

STATE_DIR = Path("/root/.backup.py")
STATE_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(log_file):
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode='a'))
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        handlers=handlers
    )


def log(msg):
    logging.info(msg)


def run(cmd, **kwargs):
    return subprocess.run(cmd, **kwargs)


def have_cmd(cmd):
    return which(cmd) is not None


def smart_install():
    log("🔧 Dependencies...")
    to_install = [
        pkg for pkg in REQUIRED_PKGS
        if "ii" not in run(
            ["dpkg", "-l", pkg],
            capture_output=True,
            text=True,
            check=False
        ).stdout
    ]
    if to_install:
        log(f"📦 {', '.join(to_install)}")
        run(["sudo", "apt", "update"], check=False)
        run(["sudo", "apt", "install", "-y"] + to_install, check=False)
    log("✅ Ready")


def docker_active():
    return run(
        ["systemctl", "is-active", "--quiet", "docker"],
        check=False
    ).returncode == 0


def docker_stop():
    log("🐳 Docker stop...")
    run(["sudo", "systemctl", "stop", "docker"], check=False)
    time.sleep(2)


def docker_start():
    log("🐳 Docker start...")
    run(["sudo", "systemctl", "start", "docker"], check=False)
    time.sleep(3)


def sql_dump():
    dumps = []
    if have_cmd("mysqldump"):
        f = "/tmp/mysql_dump.sql"
        log(f"🗄️ MySQL → {f}")
        run(
            f"sudo mysqldump --all-databases --single-transaction > {shlex.quote(f)}",
            shell=True,
            check=False
        )
        if Path(f).exists():
            dumps.append(f)
    if have_cmd("pg_dumpall"):
        f = "/tmp/postgres_dump.sql"
        log(f"🗄️ PG → {f}")
        run(
            f"sudo -u postgres pg_dumpall > {shlex.quote(f)}",
            shell=True,
            check=False
        )
        if Path(f).exists():
            dumps.append(f)
    return dumps


def sql_restore():
    for f, cmd in [
        ("/tmp/mysql_dump.sql", "mysql"),
        ("/tmp/postgres_dump.sql", "psql")
    ]:
        p = Path(f)
        if p.exists() and have_cmd(cmd):
            log(f"🗄️ Restore {cmd}")
            run(
                f"sudo {'-u postgres ' if cmd=='psql' else ''}{cmd} < {shlex.quote(str(p))}",
                shell=True
            )
            p.unlink(missing_ok=True)


def save_system_state():
    log("📋 State save...")
    run(
        f"dpkg --get-selections > {STATE_DIR / 'packages.list'}",
        shell=True,
        check=False
    )
    run(
        f"systemctl list-unit-files --state=enabled > {STATE_DIR / 'services.list'}",
        shell=True,
        check=False
    )
    run(
        f"crontab -l > {STATE_DIR / 'crontab.backup'} 2>/dev/null",
        shell=True,
        check=False
    )


def restore_system_state():
    log("🔧 State restore...")
    pkg = STATE_DIR / "packages.list"
    if pkg.exists():
        run(f"sudo dpkg --set-selections < {pkg}", shell=True)
        run(["sudo", "apt-get", "dselect-upgrade", "-y"], check=False)

    svc = STATE_DIR / "services.list"
    if svc.exists():
        run(["sudo", "systemctl", "daemon-reload"])
        for line in open(svc, encoding="utf-8", errors="ignore"):
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "enabled":
                run(["sudo", "systemctl", "enable", parts[0]], check=False)

    cron = STATE_DIR / "crontab.backup"
    if cron.exists():
        run(f"crontab {cron}", shell=True)


def maybe_fix_lxd_agent():
    if Path("/dev/vsock").exists():
        log("🖥️ LXD fix...")
        run(["sudo", "apt-get", "install", "-y", "lxd-agent-loader"], check=False)
        run(["sudo", "systemctl", "start", "lxd-agent"], check=False)


class LiveTail:
    def __init__(self, lines: int = 5):
        self.lines = lines
        self.buf = deque(maxlen=lines)
        self.percent = None
        self.ansi = sys.stdout.isatty()
        if self.ansi:
            # Резервируем место под (progress + N строк) под текущим курсором
            print("\n" * (lines + 1), end="")
            sys.stdout.flush()

    def update(self, line: str):
        line = line.rstrip("\n")
        if not line:
            return

        # Вытаскиваем проценты, если есть
        m = re.search(r"(\d{1,3})%", line)
        if m:
            self.percent = m.group(1)

        self.buf.append(line)

        # Если не TTY (лог в файл / pipe) — просто печатаем
        if not self.ansi:
            print(line)
            return

        # Двигаем курсор ВВЕРХ на (lines + 1) строк и перерисовываем блок
        up = self.lines + 1
        sys.stdout.write(f"\033[{up}F")  # move cursor up

        # Строка прогресса
        pct = self.percent or "--"
        sys.stdout.write("\033[2K")      # clear line
        sys.stdout.write(f"Progress: {pct}%\n")

        # Последние N строк
        buf_list = list(self.buf)
        for i in range(self.lines):
            sys.stdout.write("\033[2K")  # clear line
            if i < len(buf_list):
                sys.stdout.write(buf_list[i][:160])
            sys.stdout.write("\n")

        sys.stdout.flush()

    def finish(self):
        # Ничего не печатаем, чтобы не сдвигать историю
        if self.ansi:
            pass


def stream_command(cmd, env=None, cwd="/", title="Process", use_live_tail=True):
    """Выполняет команду, показывает live-tail (если use_live_tail=True)
    или просто прокидывает вывод."""
    print(f"\n=== {title} ===")

    if use_live_tail and sys.stdout.isatty():
        tail = LiveTail()
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        try:
            for line in iter(proc.stdout.readline, ""):
                tail.update(line)
        finally:
            proc.stdout.close()
            proc.wait()
            tail.finish()
    else:
        # Без LiveTail — обычный вывод, без ANSI-магии
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=cwd,
            check=False
        )

    if proc.returncode:
        log(f"❌ Exit {proc.returncode}")
        sys.exit(1)
    log("✅ OK")


def build_env(args):
    env = os.environ.copy()
    env["BORG_REPO"] = args.repo
    if args.key:
        key = Path(args.key).expanduser()
        if not key.exists():
            print(f"❌ {key}")
            sys.exit(2)
        env["BORG_RSH"] = (
            f"ssh -i {shlex.quote(str(key))} -o StrictHostKeyChecking=no"
        )
    passphrase = (
        args.password
        or os.environ.get("BORG_PASSPHRASE")
        or getpass.getpass("🔐 Passphrase: ")
    )
    env["BORG_PASSPHRASE"] = passphrase
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return env


def init_repo(env):
    if run(["borg", "list"], env=env, capture_output=True, check=False).returncode:
        log("➕ Init...")
        run(["borg", "init", "--encryption", "repokey-blake2"], env=env)


def list_archives(env):
    r = run(
        ["borg", "list", "--format", "{archive}{TAB}{time}{NL}"],
        env=env,
        capture_output=True,
        text=True
    )
    if r.returncode or not r.stdout.strip():
        print("No archives")
        return []
    print("\n📋 Archives:")
    print("─" * 60)
    archives = []
    for i, line in enumerate(
        [x.strip() for x in r.stdout.splitlines() if x.strip()], 1
    ):
        parts = line.split("\t")
        name = parts[0]
        t = parts[1] if len(parts) > 1 else ""
        print(f"{i}. {name:<40} {t}")
        archives.append(name)
    print("─" * 60)
    return archives


def select_archive(env):
    archives = list_archives(env)
    if not archives:
        sys.exit(1)
    while True:
        c = input("Archive (num/name/Enter=last): ").strip()
        if not c:
            return archives[-1]
        try:
            idx = int(c) - 1
            if 0 <= idx < len(archives):
                return archives[idx]
        except ValueError:
            pass
        if c in archives:
            return c
        print("❌ Invalid")


def archive_info(env, archive):
    print(f"\n📊 {archive}")
    stream_command(["borg", "info", f"::{archive}"], env=env, title="Info")
    stream_command(
        ["borg", "list", f"::{archive}", "--last", "5"],
        env=env,
        title="Last 5"
    )


def clear_all(env):
    print(f"⚠️ DELETE ALL {env['BORG_REPO']}?")
    if input("Write 'DELETE ALL' and press ENTER: ").strip() != "DELETE ALL":
        return

    print("👉 Now running: borg delete ...")
    stream_command(
        ["borg", "delete", "--progress", "--stats", "--glob-archives", "*"],
        env=env,
        title="DELETE",
        use_live_tail=False  # важно: без LiveTail, чтобы не было сдвига вверх
    )

    print("👉 Now running: borg compact ...")
    stream_command(
        ["borg", "compact"],
        env=env,
        title="Compact",
        use_live_tail=False  # тоже без LiveTail
    )


def do_backup(env, all_mode):
    docker = all_mode and docker_active()
    if docker:
        docker_stop()
    if all_mode:
        save_system_state()
    sql = sql_dump() if all_mode else []
    archive = (
        f"{socket.gethostname().split('.')[0]}-"
        f"{time.strftime('%Y-%m-%d_%H-%M-%S')}"
    )
    excludes = BASE_EXCLUDES + (IDENTITY_EXCLUDES if all_mode else [])
    cmd = [
        "borg", "create", f"::{archive}", "/",
        "--stats", "--progress",
        "--compression", "zstd,6",
        "--exclude-caches"
    ] + sum([["--exclude", ex] for ex in excludes], [])
    stream_command(cmd, env=env, title=f"BACKUP {archive}")
    archive_info(env, archive)
    for f in sql:
        Path(f).unlink(missing_ok=True)
    if docker:
        docker_start()


def do_restore(env, target, all_mode):
    tp = Path(target).resolve()
    if not tp.exists():
        print(f"❌ {tp}")
        sys.exit(2)
    archive = select_archive(env)
    archive_info(env, archive)
    print(f"🎯 {tp}")
    if input("Overwrite? y/N: ").lower() != 'y':
        return
    cmd = [
        "sudo", "-E", "borg", "extract", f"::{archive}",
        "--list", "--progress"
    ] + sum([["--exclude", ex] for ex in DEFAULT_RESTORE_EXCLUDES], [])
    stream_command(cmd, env=env, cwd=str(tp), title="RESTORE")
    if all_mode:
        sql_restore()
        restore_system_state()
        maybe_fix_lxd_agent()
    log("✅ Reboot?")


def main():
    p = argparse.ArgumentParser(description="BorgBackup")
    p.add_argument("--repo", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--password")
    p.add_argument("--target", default="/")
    p.add_argument("--log")
    p.add_argument("--all", action="store_true")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--backup", action="store_true")
    g.add_argument("--restore", action="store_true")
    g.add_argument("--clear-all", action="store_true")
    args = p.parse_args()

    log_file = Path.cwd() / args.log if args.log else None
    if log_file:
        log_file.parent.mkdir(exist_ok=True)

    setup_logging(log_file)
    log(f"Start: {sys.argv}")

    smart_install()
    env = build_env(args)
    init_repo(env)

    if args.list:
        list_archives(env)
    elif args.clear_all:
        clear_all(env)
    elif args.backup:
        do_backup(env, args.all)
    elif args.restore:
        do_restore(env, args.target, args.all)


if __name__ == "__main__":
    main()
