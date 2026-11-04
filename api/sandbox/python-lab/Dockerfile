# Sandbox image for Python challenges: FastAPI + a private PostgreSQL server.
# Built once with network access; jobs run it with --network none, read-only,
# as nobody. Rebuild and bump the tag when changing anything here.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s "$(ls -d /usr/lib/postgresql/*/bin)" /opt/pgbin

RUN pip install --no-cache-dir \
      "fastapi==0.115.14" "pydantic==2.11.7" "httpx==0.28.1" "psycopg[binary]==3.2.9"

# Pre-initialised cluster template owned by nobody. At run time a test driver
# copies it into /tmp (tmpfs) and starts PostgreSQL on a Unix socket only.
RUN mkdir /opt/pgtemplate && chown 65534:65534 /opt/pgtemplate \
 && su -s /bin/sh nobody -c "/opt/pgbin/initdb -D /opt/pgtemplate -A trust -U forge --no-sync -E UTF8 --wal-segsize=1 >/dev/null" \
 && printf "%s\n" \
      "listen_addresses = ''" \
      "unix_socket_directories = '/tmp'" \
      "max_connections = 30" \
      "shared_buffers = 16MB" \
      "dynamic_shared_memory_type = mmap" \
      "fsync = off" "synchronous_commit = off" "full_page_writes = off" \
      "logging_collector = off" \
    >> /opt/pgtemplate/postgresql.conf \
 && chmod -R go-rwx /opt/pgtemplate

ENV PYTHONDONTWRITEBYTECODE=1
