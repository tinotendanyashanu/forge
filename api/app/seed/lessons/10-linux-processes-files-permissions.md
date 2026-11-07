+++
slug = "linux-processes-files-permissions"
skill = "linux"
topic = "processes"
difficulty = "beginner"
title = "Linux: processes, files and permissions"
summary = "The Linux concepts every backend engineer uses daily: the filesystem, permissions, processes, signals, environment variables and exit codes."
estimated_minutes = 24
objectives = [
  "Read and set file permissions and ownership, and explain why least privilege matters.",
  "Inspect processes, send signals, and explain how services stop gracefully.",
  "Use environment variables, standard streams and exit codes in scripts and services.",
]
prerequisites = []
misconceptions = [
  "Running services as root is fine on a private server.",
  "kill always stops a process immediately.",
  "Files a container writes are kept when the container is replaced.",
]
checks = ["linux-octal-mode", "linux-kill-default-signal", "linux-redirect-truncate"]
status = "reviewed"
version = 2
provenance = "ai-assisted draft (Claude), self-reviewed; commands checked on Ubuntu 24.04; pending independent human review"

[[resources]]
title = "Ubuntu tutorial: The Linux command line for beginners"
url = "https://ubuntu.com/tutorials/command-line-for-beginners"

[[resources]]
title = "Linux man pages: chmod(1)"
url = "https://man7.org/linux/man-pages/man1/chmod.1.html"

[[resources]]
title = "Linux man pages: signal(7)"
url = "https://man7.org/linux/man-pages/man7/signal.7.html"

[[resources]]
title = "systemd docs: systemd.service"
url = "https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html"
+++
## Why it matters

Almost every server, container and CI runner you will deploy to is Linux. When a service will not start, cannot read its config, ignores a shutdown, or leaks a secret through the environment, the cause is usually one of a handful of operating-system concepts. Knowing them turns "it works on my machine" into a five-minute diagnosis.

## Mental model

On Linux, almost everything is either a **file** or a **process**.

- Files live in one tree starting at `/`. Configuration is in `/etc`, logs in `/var/log`, temporary files in `/tmp`, and each user's files in `/home/<user>`.
- Every file has an **owner**, a **group** and **permission bits** saying who may read, write or execute it.
- A process is a running program with a **PID**, a **user** it runs as, an **environment**, three standard streams (stdin, stdout, stderr), and, when it ends, an **exit code**.

## How it works

**Permissions.** `ls -l` shows something like `-rw-r----- 1 forge forge 512 config.env`: the owner may read and write, the group may read, others have no access. In octal, read is 4, write 2, execute 1, so that file is `640`. `chmod 640 config.env` sets it; `chown forge:forge config.env` sets owner and group. For directories, execute means "may enter".

**Least privilege.** Run each service as its own unprivileged user that can read only what it needs. Then a bug in that service cannot overwrite system files or read other services' secrets.

**Processes and signals.** `ps aux` and `top` list processes. `kill <pid>` sends `SIGTERM`, a polite request to stop that programs can handle to finish work and clean up. `kill -9 <pid>` sends `SIGKILL`, which the kernel enforces immediately with no cleanup. Service managers such as systemd (and container runtimes) send `SIGTERM` first, wait, then send `SIGKILL`.

**Environment, streams and exit codes.** Environment variables (`DATABASE_URL=...`) configure a process without changing code. Programs write normal output to stdout and errors to stderr; `cmd > out.txt 2> err.txt` separates them, and `|` pipes stdout into another program. Exit code `0` means success; anything else is failure, which is how scripts and CI decide whether to continue (`set -e` in a shell script stops at the first failure).

## Worked example

A minimal systemd unit for an API, running as its own user:

```ini
[Unit]
Description=Example API
After=network-online.target

[Service]
User=api
Group=api
EnvironmentFile=/etc/api/api.env
ExecStart=/opt/api/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown root:api /etc/api/api.env
sudo chmod 640 /etc/api/api.env      # root writes, the api group reads, others nothing
sudo systemctl enable --now api      # start now and at boot
systemctl status api                 # running? recent log lines?
journalctl -u api -n 50              # the last 50 log lines
echo $?                              # exit code of the previous command
```

On `systemctl stop api`, systemd sends `SIGTERM`; uvicorn stops accepting connections and finishes in-flight requests before exiting.

## Common mistakes

- `chmod 777` to "fix" a permission error. It gives every user write access; find the right owner and minimal mode instead.
- Running application services as `root`.
- Putting secrets on the command line, where any user can see them with `ps`. Use a protected environment file or a secret store.
- Using `kill -9` first, so the program never cleans up (temporary files, open transactions, lock files).
- Writing important data inside a container's filesystem, which is discarded when the container is replaced.

## In production

Containers are ordinary Linux processes with isolation features (namespaces and cgroups) around them. The same rules apply inside: run as a non-root user, handle `SIGTERM` for graceful shutdown (orchestrators send it before killing), log to stdout and stderr so the platform collects logs, and keep persistent data in volumes or external storage.

## Trade-offs and limits

Strict permissions and dedicated users add setup work and occasionally block legitimate access, which you fix by granting exactly what is needed, not everything. Environment variables are simple and universal but visible to anything running as the same user and easy to leak in debug output, so sensitive deployments move to dedicated secret stores. `SIGTERM` handling only helps if the application implements it.

## Check your understanding

1. What does mode `640` allow?
   - Answer: owner read and write, group read, others nothing.
2. What is the difference between `SIGTERM` and `SIGKILL`?
   - Answer: `SIGTERM` asks the process to stop and can be handled for cleanup; `SIGKILL` stops it immediately and cannot be caught.
3. A CI step's script ends with exit code 1. What happens to the pipeline?
   - Answer: the step is marked failed and, by default, later steps do not run.

## Practice

On a Linux machine or container, create a user `appuser` and a file only that user can read. Write a short Python script that prints an environment variable, logs a line to stderr, sleeps, and handles `SIGTERM` by printing "shutting down" before exiting with code 0. Run it as `appuser`, stop it with `kill`, and check the exit code. Then stop it with `kill -9` and compare.
