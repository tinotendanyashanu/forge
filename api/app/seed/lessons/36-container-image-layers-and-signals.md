+++
slug = "container-image-layers-and-signals"
skill = "devops"
topic = "containers"
difficulty = "beginner"
title = "Containers: image layers, writable state and process signals"
summary = "Build images so dependency layers stay cached, keep durable data out of a container's writable layer, and make PID 1 receive the signal that should stop the process."
estimated_minutes = 35
objectives = ["Explain when a Docker build reuses a layer and when a source change invalidates later steps.", "Choose a volume or external store for data that must survive a new container.", "Contrast shell-form and exec-form commands when a service handles SIGTERM."]
prerequisites = ["safe-delivery-and-observability", "linux-processes-files-permissions"]
misconceptions = ["Any small source edit must reinstall dependencies because the whole image is one blob.", "Files written inside a container are kept when a new container is created from the same image.", "A shell-form command and an exec-form command handle stop signals in the same way."]
checks = ["devops-docker-layer-order", "devops-container-ephemeral-fs", "devops-shell-form-sigterm"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; Docker example executed locally against the already present python:3.12-slim image; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Docker: build cache"
url = "https://docs.docker.com/build/cache/"
[[resources]]
title = "Dockerfile shell and exec form"
url = "https://docs.docker.com/reference/dockerfile/#shell-and-exec-form"
[[resources]]
title = "Docker: volumes"
url = "https://docs.docker.com/engine/storage/volumes/"
+++
## Why it matters

A four-minute dependency install on every one-line change makes a pipeline feel broken even when the application code is fine. A deployment that stores uploads inside the container then looks like data loss: the new container comes up healthy and the files are simply not there. A process that handles SIGTERM in Python still sits until the platform kills it, because the signal never reached Python. These are ordinary container failures, and they come from mixing up the image, the writable layer, and which process is PID 1.

Prerequisites: the safe-delivery lesson's idea of building one artifact and promoting it, and the Linux lesson's idea that a process receives signals. You do not need a cluster. The example uses a local Docker engine and the `python:3.12-slim` image that is already present. It does not enable FORGE's coding sandbox, and it removes the containers it creates.

## Mental model

An image is a stack of layers. Each Dockerfile instruction can produce a layer. Docker reuses a layer only when that instruction and every instruction before it still match the cache. A changed instruction invalidates itself and everything after it. Copying the whole source tree before installing dependencies means a source edit invalidates the install. Copying the dependency manifest first, installing, and only then copying the source keeps the install cached until the manifest changes.

A running container adds a writable layer on top of the image. Writes in that layer belong to that container. Replacing the container starts again from the image. A volume or an external object store is what survives replacement. The image is the recipe and the starting filesystem. It is not the place where user uploads live.

PID 1 is the process the platform signals when it wants the container to stop. Exec form, `CMD ["python", "service.py"]`, runs Python as PID 1, so a handler installed in Python can see SIGTERM. Shell form, `CMD python service.py`, runs a shell as PID 1 and Python as its child. In the example below, SIGTERM reached the shell and did not reach Python. Docker's stop sequence sends SIGTERM and, after a grace period, SIGKILL. The Docker reference documents that grace period. This lesson's run did not wait out a full stop timeout; it sent SIGTERM and observed whether the handler ran.

## How it works

Order the Dockerfile from least volatile to most volatile. Base image, then dependency files, then the install, then application source, then the command. A comment-only source change should rebuild the source layer and reuse the install. A dependency change should rebuild from the install downward. Cache is a build-time speedup, not a correctness proof: a cached layer can still be the wrong layer if an earlier instruction was edited without changing its visible text, or if the build used a different context.

Persistent files need a location outside the writable layer. A mounted volume is enough when one host owns the data and you accept that host as the storage boundary. Several replaceable instances need a store they can all reach, such as object storage, because a volume local to one machine does not follow an instance that starts somewhere else. Putting the path in the image with `COPY` only ships the files that existed at build time.

For shutdown, log the real PID 1. If it is a shell, the application handler is not the process being signalled. Prefer exec form unless you specifically need a shell to expand variables, and even then an entrypoint script that ends with `exec` can replace the shell so the application becomes PID 1. Also handle the signal in the application: close listeners, finish or reject in-flight work, and exit. A handler that ignores the signal still produces a hard kill after the grace period.

## Worked example

The script builds an image twice. The second build appends a unique comment to the source file, so that layer cannot be reused, while the dependency `RUN` is unchanged. It then writes a file in one container and checks that a new container does not have it. Finally it compares exec form and shell form under SIGTERM. Run it only where Docker is available and `python:3.12-slim` is already local. It deletes the containers and images it creates.

```bash
#!/bin/bash
set -eu
root=$(mktemp -d)
cleanup() {
  docker rm -f p7-upload p7-exec p7-shell >/dev/null 2>&1 || true
  docker rmi p7-cache:1 p7-exec:1 p7-shell:1 >/dev/null 2>&1 || true
  rm -rf "$root"
}
trap cleanup EXIT
cd "$root"
mkdir -p app
printf 'marker\n' > app/marker.txt
cat > app/service.py << 'PY'
import os, signal, sys, time
print("pid %s" % os.getpid(), flush=True)
def stop(signum, frame):
    print("got-term", flush=True)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
while True:
    time.sleep(0.2)
PY
cat > app/Dockerfile << 'EOF'
FROM python:3.12-slim
WORKDIR /app
COPY marker.txt /app/marker.txt
RUN python -c "open('/app/layer-stamp','w').write('deps')"
COPY service.py /app/service.py
CMD ["python", "/app/service.py"]
EOF
docker build --pull=false -f app/Dockerfile -t p7-cache:1 app >/tmp/p7-first-build.log 2>&1
token=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
printf '\n# %s\n' "$token" >> app/service.py
docker build --pull=false -f app/Dockerfile -t p7-cache:1 app >/tmp/p7-second-build.log 2>&1
layer_result() {
  awk -v pattern="$1" '
    $0 ~ pattern { id=$1; seen=1 }
    seen && $1==id && /CACHED/ { result="cached" }
    seen && $1==id && /DONE/ { result="rebuilt" }
    END { print (result == "" ? "unknown" : result) }
  ' /tmp/p7-second-build.log
}
echo "dependency_layer $(layer_result 'RUN python')"
echo "source_layer $(layer_result 'COPY service.py')"

docker run -d --name p7-upload --pull=never python:3.12-slim python -c 'import time; open("/tmp/upload","w").write("photo"); time.sleep(30)' >/dev/null
same=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  same=$(docker exec p7-upload python -c 'print(open("/tmp/upload").read())' 2>/dev/null || true)
  [ -n "$same" ] && break
  sleep 0.3
done
docker rm -f p7-upload >/dev/null
fresh=$(docker run --rm --pull=never python:3.12-slim python -c 'import os; print(os.path.exists("/tmp/upload"))')
echo "same_container $same"
echo "new_container $fresh"

cat > app/Dockerfile.exec << 'EOF'
FROM python:3.12-slim
COPY service.py /app/service.py
CMD ["python", "/app/service.py"]
EOF
cat > app/Dockerfile.shell << 'EOF'
FROM python:3.12-slim
COPY service.py /app/service.py
CMD python /app/service.py
EOF
docker build --pull=false -q -f app/Dockerfile.exec -t p7-exec:1 app >/dev/null
docker build --pull=false -q -f app/Dockerfile.shell -t p7-shell:1 app >/dev/null
probe() {
  name=$1
  image=$2
  label=$3
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --pull=never "$image" >/dev/null
  pid=""
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    pid=$(docker logs "$name" 2>&1 | awk '/^pid /{print $2; exit}')
    [ -n "$pid" ] && break
    sleep 0.2
  done
  pid1=$(docker top "$name" -o pid,cmd | awk 'NR==2 {print $2}')
  docker kill --signal=TERM "$name" >/dev/null || true
  sleep 0.8
  if docker logs "$name" 2>&1 | grep -q '^got-term$'; then signal=got-term; else signal=absent; fi
  state=$(docker inspect -f '{{.State.Status}}' "$name")
  echo "${label}_pid1 $pid1"
  echo "${label}_signal $signal"
  echo "${label}_state $state"
  docker rm -f "$name" >/dev/null
}
probe p7-exec p7-exec:1 exec
probe p7-shell p7-shell:1 shell
```

```text
dependency_layer cached
source_layer rebuilt
same_container photo
new_container False
exec_pid1 python
exec_signal got-term
exec_state exited
shell_pid1 /bin/sh
shell_signal absent
shell_state running
```

The dependency instruction was cached after the source comment changed. The same container read `photo`. A new container did not have that file. Exec form made Python PID 1, and the handler printed `got-term` and exited. Shell form made `/bin/sh` PID 1. SIGTERM did not produce `got-term`, and that container was still running when inspected. This was observed with Docker's shell form on `python:3.12-slim`, not as a claim about every init system.

## Common mistakes

- Copying the entire build context before installing dependencies, then blaming the package index for a cache that never had a chance.
- Treating `docker commit` or a file written at runtime as a backup. The next deployment builds or pulls an image and starts a new container.
- Assuming a volume mount and a host path are portable across machines. A path on one node is not a shared disk.
- Running the server under a shell and testing only `docker kill` of the child process. The platform signals PID 1.
- Using `--cache-from` or a registry cache without checking which layers actually matched. A green build can still have rebuilt the expensive step.

## In production

Build the image once in CI and deploy that digest. Rebuilding on the production host with whatever is in the working tree is a different artifact. Pin base images by digest when you need a repeatable build, and still rebuild on a schedule so you take security updates deliberately.

Put uploads, caches that must survive restart, and local databases on a volume or a managed store. Do not put secrets in image layers. A later stage that deletes a secret file does not remove it from the earlier layer. Pass secrets at runtime or through the build's secret mount, and keep them out of `docker history`.

Set a stop grace period long enough for the process to drain, and short enough that a stuck process cannot block a rollout forever. Log when the handler starts and when the process exits. If stops regularly reach the kill timeout, inspect PID 1 before raising the timeout. A longer timeout does not fix a shell that swallows the signal.

## Trade-offs and limits

Layer cache makes builds fast and can also hide stale assumptions. A dependency lockfile that did not change can still resolve differently if the install command reaches a network and the index moved. For a reproducible install, use a lockfile and a frozen install, and accept that you will rebuild when you update the lock.

Volumes are simple and local. Object storage adds latency and a new failure domain, and it is the usual way to share uploads across instances. A database inside a container with a volume is a reasonable local development setup and a poor default for production unless someone owns its backups, disk, and failover.

Exec form does not by itself make shutdown correct. The process must handle the signal, and workers or child processes must be stopped on purpose. A minimal init can reap zombies and forward signals when the process model is more than one process. This lesson does not configure Kubernetes, a specific orchestrator grace-period field, or a multi-stage production Dockerfile. Those are the next design choices after the three mechanisms here are clear.

## Check your understanding

1. A source file changes and the dependency install runs again. What likely sits above the install in the Dockerfile?
   - Feedback: an instruction that changes when the source changes, often `COPY` of the whole context. Later steps, including the install, are rebuilt when an earlier step misses the cache.
2. Why can two containers from the same image disagree about whether an upload exists?
   - Feedback: the upload was written in one container's writable layer. The image they share does not contain it, so the other container starts without that file.
3. The application logs a SIGTERM handler, but a stop never prints that log. What should you inspect first?
   - Feedback: which process is PID 1. If a shell is PID 1, the handler in the child is not the process that received the platform's signal.

## Practice

Write a cache-friendly toy Dockerfile for a local Python script: copy a requirements file, install it, then copy the script. This is a single build stage; separate cache layers do not make a multi-stage build. Change only the script and confirm the install layer is cached. Change the requirements file and confirm the install runs again. In a second exercise, run a container that writes `/tmp/note`, remove it, and show that a new container does not contain the note. In a third, print PID 1 for both command forms.

Acceptance criteria: the install layer stays cached across a source-only change and rebuilds after a dependency change; no upload or note is stored only in the writable layer if it must survive replacement; exec form shows the application as PID 1 and shell form shows a shell. Do not point the example at a production registry or a real data volume. As a transfer task, explain why baking an uploaded file into an image with `docker commit` would still be the wrong durability plan for more than one instance.
