"""Execution backends. Used only by the worker process, never by the API server.

* ``disabled`` — nothing runs.
* ``mock``     — executes nothing; every test is reported as not executed.
* ``docker``   — one hardened, ephemeral container per job. Container isolation
  is NOT adequate for hostile multi-user workloads; this backend refuses to
  start unless FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true acknowledges a
  local, single-user deployment, and it refuses jobs unless its in-sandbox
  self-verification passes.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.coding.grading import CaseSpec
from app.core.config import Settings

HARNESS_DIR = Path(__file__).resolve().parent / "harness"
SOURCE_FILE = {"python": "solution.py", "javascript": "solution.mjs", "typescript": "solution.ts"}
DRIVER_FILE = {"python": "driver.py", "javascript": "driver.mjs", "typescript": "driver.mjs"}
STARTUP_ALLOWANCE_MS = 2500


class SandboxUnavailable(Exception):
    """Infrastructure problem (daemon down, image missing). Retryable."""


@dataclass
class ExecRequest:
    language: str
    code: str
    driver: str | None
    cases: list[CaseSpec]
    time_limit_ms: int
    memory_limit_mb: int


@dataclass
class ProjectExecRequest:
    """One suite of an engineering project: a file tree plus trusted checks.

    ``visibility`` decides which checks are staged: public runs never contain the
    hidden checks file, so learner code can't read hidden inputs and echo them
    through a public result.
    """

    suite: str  # python | node
    visibility: str  # public | hidden
    files: dict[str, str]
    checks: dict[str, str]  # "public"/"hidden" -> trusted source
    cases: list[CaseSpec]
    time_limit_ms: int
    memory_limit_mb: int


@dataclass
class ExecResult:
    stdout: str
    exit_code: int | None
    killed_for_time: bool
    output_truncated: bool
    duration_ms: int


@dataclass
class Verification:
    backend: str
    verified: bool
    executes: bool
    languages: dict[str, bool] = field(default_factory=dict)
    checks: dict[str, dict[str, bool]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        return self.__dict__.copy()


class DisabledSandbox:
    name = "disabled"
    executes = False

    async def verify(self) -> Verification:
        return Verification("disabled", False, False, problems=["Code execution is disabled"])

    async def run(self, req: ExecRequest) -> ExecResult:
        raise SandboxUnavailable("Code execution is disabled")

    async def run_project(self, req: "ProjectExecRequest") -> ExecResult:
        raise SandboxUnavailable("Code execution is disabled")


class MockSandbox:
    """Executes nothing. Exists so the UI and job flow can be exercised safely."""

    name = "mock"
    executes = False

    async def verify(self) -> Verification:
        return Verification(
            "mock", True, False, languages={k: True for k in SOURCE_FILE},
            problems=["Mock runner: submitted code is never executed"],
        )

    async def run(self, req: ExecRequest) -> ExecResult:
        return ExecResult("", 0, False, False, 0)

    async def run_project(self, req: "ProjectExecRequest") -> ExecResult:
        return ExecResult("", 0, False, False, 0)


# ---------------------------------------------------------------- docker


PROBE_PY = r'''
import json, os, socket, subprocess
c = {}
c["non_root"] = os.getuid() != 0 and os.geteuid() != 0
def cap_eff():
    for line in open("/proc/self/status"):
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
c["no_capabilities"] = cap_eff() == 0
# Kernels create inert fallback tunnel devices (gre0, sit0, ...) in every
# namespace. They are down and can't be raised without CAP_NET_ADMIN, so the
# requirement is: nothing but loopback is administratively up.
def up(i):
    p = f"/sys/class/net/{i}"
    return os.path.isdir(p) and int(open(p + "/flags").read(), 16) & 0x1
c["only_loopback_up"] = [i for i in os.listdir("/sys/class/net") if up(i)] == ["lo"]
try:
    socket.create_connection(("1.1.1.1", 53), timeout=2).close(); c["outbound_blocked"] = False
except OSError:
    c["outbound_blocked"] = True
def cannot_write(path):
    try:
        open(path, "w").write("x"); return False
    except OSError:
        return True
c["root_fs_read_only"] = cannot_write("/forge-probe")
c["work_dir_read_only"] = cannot_write("/work/forge-probe")
try:
    open("/tmp/p.sh", "w").write("#!/bin/sh\necho hi\n"); os.chmod("/tmp/p.sh", 0o755)
    subprocess.run(["/tmp/p.sh"], check=True, capture_output=True); c["tmp_noexec"] = False
except (OSError, subprocess.CalledProcessError):
    c["tmp_noexec"] = True
c["no_docker_socket"] = not os.path.exists("/var/run/docker.sock")
c["no_host_secrets_in_env"] = not any(k.startswith(("FORGE_", "DATABASE", "PG", "AWS_", "OLLAMA")) for k in os.environ)
def read(p):
    try: return open(p).read().strip()
    except OSError: return ""
c["memory_limited"] = read("/sys/fs/cgroup/memory.max") not in ("", "max")
c["swap_disabled"] = read("/sys/fs/cgroup/memory.swap.max") in ("0", "")
c["pids_limited"] = read("/sys/fs/cgroup/pids.max") not in ("", "max")
print("@@PROBE@@" + json.dumps(c))
'''

PROBE_JS = r'''
import fs from "node:fs";
import net from "node:net";
const c = {};
c.non_root = process.getuid() !== 0 && process.geteuid() !== 0;
const capEff = fs.readFileSync("/proc/self/status", "utf8").split("\n").find((l) => l.startsWith("CapEff:"));
c.no_capabilities = BigInt("0x" + capEff.split(/\s+/)[1]) === 0n;
const isUp = (i) => {
  const p = `/sys/class/net/${i}`;
  try { return fs.statSync(p).isDirectory() && (parseInt(fs.readFileSync(p + "/flags", "utf8"), 16) & 1) === 1; } catch { return false; }
};
c.only_loopback_up = JSON.stringify(fs.readdirSync("/sys/class/net").filter(isUp)) === '["lo"]';
c.outbound_blocked = await new Promise((resolve) => {
  const s = net.connect({ host: "1.1.1.1", port: 53, timeout: 2000 });
  s.on("connect", () => { s.destroy(); resolve(false); });
  s.on("error", () => resolve(true));
  s.on("timeout", () => { s.destroy(); resolve(true); });
});
const cannotWrite = (p) => { try { fs.writeFileSync(p, "x"); return false; } catch { return true; } };
c.root_fs_read_only = cannotWrite("/forge-probe");
c.work_dir_read_only = cannotWrite("/work/forge-probe");
c.no_docker_socket = !fs.existsSync("/var/run/docker.sock");
c.no_host_secrets_in_env = !Object.keys(process.env).some((k) => /^(FORGE_|DATABASE|PG|AWS_|OLLAMA)/.test(k));
const read = (p) => { try { return fs.readFileSync(p, "utf8").trim(); } catch { return ""; } };
c.memory_limited = !["", "max"].includes(read("/sys/fs/cgroup/memory.max"));
c.swap_disabled = ["0", ""].includes(read("/sys/fs/cgroup/memory.swap.max"));
c.pids_limited = !["", "max"].includes(read("/sys/fs/cgroup/pids.max"));
process.stdout.write("@@PROBE@@" + JSON.stringify(c) + "\n");
'''


class DockerSandbox:
    name = "docker"
    executes = True

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.images = {
            "python": settings.sandbox_python_image,
            "javascript": settings.sandbox_node_image,
            "typescript": settings.sandbox_node_image,
        }

    # -- command construction (unit-tested) ------------------------------------

    def docker_args(self, name: str, work_dir: str, image: str, memory_mb: int) -> list[str]:
        memory_mb = min(memory_mb, self.s.sandbox_max_memory_mb)
        return [
            "docker", "run", "--rm", "--name", name,
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", str(self.s.sandbox_pids_limit),
            "--memory", f"{memory_mb}m", "--memory-swap", f"{memory_mb}m",
            "--cpus", "1",
            "--user", "65534:65534",
            "--ipc", "none",
            "--ulimit", "nofile=64:64",
            # Max size of any single file written (tmpfs is also memory-bounded).
            "--ulimit", "fsize=8388608:8388608",
            # tmpfs pages count against the same memory cgroup limit.
            "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={max(16, min(memory_mb, 128))}m",
            "--mount", f"type=bind,source={work_dir},target=/work,readonly",
            "--workdir", "/tmp",
            "--env", "HOME=/tmp",
            "--hostname", "sandbox",
            "--log-driver", "none",
            "--stop-timeout", "1",
            image,
        ]

    def command(self, language: str, per_case_ms: int, memory_mb: int) -> list[str]:
        if language == "python":
            return ["python", "-I", "-B", "/work/harness.py", str(per_case_ms)]
        ext = "ts" if language == "typescript" else "mjs"
        heap = max(16, int(min(memory_mb, self.s.sandbox_max_memory_mb) * 0.6))
        return [
            "node", f"--max-old-space-size={heap}", "--disallow-code-generation-from-strings",
            "/work/harness.mjs", str(per_case_ms), ext,
        ]

    def wall_clock_ms(self, req: ExecRequest) -> int:
        budget = req.time_limit_ms * max(1, len(req.cases)) + STARTUP_ALLOWANCE_MS
        return min(budget, self.s.sandbox_max_time_ms + STARTUP_ALLOWANCE_MS)

    # -- execution ----------------------------------------------------------------

    async def _exec(self, args: list[str], name: str, wall_ms: int) -> ExecResult:
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailable("docker CLI not found") from exc
        limit = self.s.sandbox_max_output_bytes
        chunks: list[bytes] = []
        size, truncated, killed = 0, False, False

        async def pump() -> None:
            nonlocal size, truncated
            assert proc.stdout is not None
            while chunk := await proc.stdout.read(8192):
                if size < limit:
                    chunks.append(chunk[: limit - size])
                size += len(chunk)
                if size > limit:
                    truncated = True
                    await self._kill(name, proc)
                    return

        try:
            await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout=wall_ms / 1000)
        except TimeoutError:
            killed = True
            await self._kill(name, proc)
        stderr = (await proc.stderr.read(4096)).decode(errors="replace") if proc.stderr else ""
        code = proc.returncode
        if code == 125 or "Cannot connect to the Docker daemon" in stderr or "Unable to find image" in stderr:
            raise SandboxUnavailable(stderr.strip()[:300] or "docker run failed")
        return ExecResult(
            b"".join(chunks).decode(errors="replace"), code, killed, truncated,
            int((time.monotonic() - start) * 1000),
        )

    async def _kill(self, name: str, proc: asyncio.subprocess.Process) -> None:
        killer = await asyncio.create_subprocess_exec(
            "docker", "kill", name, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await killer.wait()
        if proc.returncode is None:
            proc.kill()
            await proc.wait()

    def _stage(self, files: dict[str, str]) -> str:
        work = tempfile.mkdtemp(prefix="forge-job-")
        os.chmod(work, 0o755)
        for name, content in files.items():
            path = os.path.join(work, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(path, 0o644)
        return work

    async def run(self, req: ExecRequest) -> ExecResult:
        per_case = min(req.time_limit_ms, self.s.sandbox_max_time_ms)
        harness = "python_harness.py" if req.language == "python" else "js_harness.mjs"
        files = {
            SOURCE_FILE[req.language]: req.code,
            ("harness.py" if req.language == "python" else "harness.mjs"): (HARNESS_DIR / harness).read_text(),
            # Inputs only. Expected values never enter the sandbox.
            "cases.json": json.dumps([{"id": c.id, "call": c.call, "args": c.args} for c in req.cases]),
        }
        if req.driver:
            files[DRIVER_FILE[req.language]] = req.driver
        work = self._stage(files)
        name = f"forge-job-{uuid.uuid4().hex[:16]}"
        try:
            args = self.docker_args(name, work, self.images[req.language], req.memory_limit_mb)
            return await self._exec(args + self.command(req.language, per_case, req.memory_limit_mb), name, self.wall_clock_ms(req))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def run_project(self, req: ProjectExecRequest) -> ExecResult:
        """Stages the project under /work/project and runs one suite's checks."""
        from app.workspace.paths import stage_tree

        language = "python" if req.suite == "python" else "javascript"
        per_case = min(req.time_limit_ms, self.s.sandbox_max_time_ms)
        work = tempfile.mkdtemp(prefix="forge-proj-")
        os.chmod(work, 0o755)
        try:
            project = os.path.join(work, "project")
            os.mkdir(project, 0o755)
            stage_tree(project, req.files)
            ext = "py" if req.suite == "python" else "mjs"
            harness = "python_project_harness.py" if req.suite == "python" else "js_project_harness.mjs"
            top = {
                f"harness.{ext}": (HARNESS_DIR / harness).read_text(),
                # Inputs only. Expected values never enter the sandbox.
                "cases.json": json.dumps([{"id": c.id, "call": c.call, "args": c.args} for c in req.cases]),
                f"checks_public.{ext}": req.checks.get("public", ""),
            }
            if req.visibility == "hidden":
                top[f"checks_hidden.{ext}"] = req.checks["hidden"]
            for fname, content in top.items():
                path = os.path.join(work, fname)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                os.chmod(path, 0o644)
            for root, dirs, _ in os.walk(work):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o755)
            if req.suite == "python":
                cmd = ["python", "-I", "-B", "/work/harness.py", str(per_case), req.visibility]
            else:
                heap = max(16, int(min(req.memory_limit_mb, self.s.sandbox_max_memory_mb) * 0.6))
                cmd = ["node", f"--max-old-space-size={heap}", "--disallow-code-generation-from-strings",
                       "/work/harness.mjs", str(per_case), req.visibility]
            name = f"forge-proj-{uuid.uuid4().hex[:16]}"
            wall = min(per_case * max(1, len(req.cases)) + STARTUP_ALLOWANCE_MS,
                       self.s.sandbox_max_time_ms + STARTUP_ALLOWANCE_MS)
            args = self.docker_args(name, work, self.images[language], req.memory_limit_mb)
            return await self._exec(args + cmd, name, wall)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def verify(self) -> Verification:
        v = Verification("docker", False, True)
        if not self.s.sandbox_allow_container_isolation:
            v.problems.append(
                "Container-only isolation not acknowledged (set FORGE_SANDBOX_ALLOW_CONTAINER_ISOLATION=true "
                "only for a local, single-user deployment)"
            )
            return v
        probes = {"python": ("probe.py", PROBE_PY, ["python", "-I", "-B", "/work/probe.py"]),
                  "node": ("probe.mjs", PROBE_JS, ["node", "/work/probe.mjs"])}
        for key, (fname, src, cmd) in probes.items():
            image = self.s.sandbox_python_image if key == "python" else self.s.sandbox_node_image
            work = self._stage({fname: src})
            name = f"forge-probe-{uuid.uuid4().hex[:12]}"
            try:
                result = await self._exec(self.docker_args(name, work, image, 64) + cmd, name, 20_000)
                line = next((l for l in result.stdout.splitlines() if l.startswith("@@PROBE@@")), None)
                checks = json.loads(line[9:]) if line else {}
            except SandboxUnavailable as exc:
                checks = {}
                v.problems.append(f"{key}: {exc}")
            finally:
                shutil.rmtree(work, ignore_errors=True)
            v.checks[key] = checks
            ok = bool(checks) and all(checks.values())
            if checks and not ok:
                v.problems.append(f"{key}: failed checks {sorted(k for k, x in checks.items() if not x)}")
            elif not checks and not any(p.startswith(key) for p in v.problems):
                v.problems.append(f"{key}: probe produced no report")
            if key == "python":
                v.languages["python"] = ok
            else:
                v.languages["javascript"] = v.languages["typescript"] = ok
        v.verified = any(v.languages.values())
        return v


def build_sandbox(settings: Settings):
    if settings.sandbox_backend == "docker":
        return DockerSandbox(settings)
    if settings.sandbox_backend == "mock":
        return MockSandbox()
    return DisabledSandbox()
