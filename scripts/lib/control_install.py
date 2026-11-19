"""Repeatable DGX host provisioning. Invoked by install-control-daemon.

The normal-user entrypoint configures the control environment; its sudo child
installs host components. Downloads are pinned and checked before execution.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import platform
import pwd
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

VERSION = "26.05.6"
SLURM_SHA = "386a0d624fa7c730cf4dfa9171bf6dc66b6816b5683242c5271879999a54a9a7"
HEADER_URL = "https://raw.githubusercontent.com/NVIDIA/go-nvml/v0.13.0-1/pkg/nvml/nvml.h"
HEADER_SHA = "2d047fe07e92e038714674fe578ae76d9ec1eca55f17e09b81fb412d67adab99"
UNITS = ("munge.service", "slurmctld.service", "slurmd.service", "slurmrestd.service")
PLUGINS = ("auth_munge", "auth_jwt", "rest_auth_jwt", "openapi_slurmctld",
           "data_parser_v0_0_45", "gpu_nvml", "cgroup_v2", "task_cgroup", "proctrack_cgroup")
PACKAGES = ("build-essential", "pkg-config", "bzip2", "ca-certificates", "python3-venv",
            "munge", "libmunge-dev", "libjwt-dev", "libjson-c-dev", "libhttp-parser-dev",
            "libyaml-dev", "libhwloc-dev", "libnuma-dev", "libdbus-1-dev", "libbpf-dev",
            "libssl-dev", "libreadline-dev")


def run(args, *, cwd=None, env=None, check=True, capture=True, timeout=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True,
                            capture_output=capture, check=False, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{shlex.join([str(a) for a in args])} failed" +
                           (": " + result.stderr.strip() if capture else "; see output above"))
    return result


def atomic(path: Path, data: bytes, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix="." + path.name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def download(url: str, digest: str, path: Path):
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return
    with urlopen(url, timeout=120) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("Downloaded artifact failed checksum/size verification: " + url)
    atomic(path, data)


def topology(output: str, reserve_mb: int) -> dict:
    lines = [line for line in output.splitlines() if line.startswith("NodeName=")]
    if len(lines) != 1:
        raise RuntimeError("slurmd -C did not report exactly one node")
    fields = dict(token.split("=", 1) for token in lines[0].split() if "=" in token)
    values = {name: int(fields[name]) for name in
              ("CPUs", "Boards", "SocketsPerBoard", "CoresPerSocket", "ThreadsPerCore", "RealMemory")}
    if any(number < 1 for number in values.values()):
        raise RuntimeError("Invalid discovered CPU/memory topology")
    if values["CPUs"] != values["Boards"] * values["SocketsPerBoard"] * values["CoresPerSocket"] * values["ThreadsPerCore"]:
        raise RuntimeError("Inconsistent CPU topology; inspect slurmd -C on the heterogeneous ARM host")
    reserve = max(reserve_mb, (values["RealMemory"] + 9) // 10)
    values["RealMemory"] -= reserve
    if values["RealMemory"] < 4096:
        raise RuntimeError("Insufficient memory after reserving host headroom")
    return values


class Provisioner:
    def __init__(self, request: dict, *, root=Path("/")):
        self.request, self.root = request, root
        self.repo = Path(request["repo"])
        self.owner = pwd.getpwnam(request["owner"])
        if self.owner.pw_uid == 0:
            raise RuntimeError("Install as the normal control user; sudo is requested for host provisioning")
        self.prefix = self.p("/opt/eliza-slurm/" + VERSION)
        self.cache = self.p("/var/cache/eliza-control-install")
        self.receipt_path = self.p("/var/lib/eliza-control-install/receipt.json")
        self.receipt = json.loads(self.receipt_path.read_text()) if self.receipt_path.exists() else {"files": {}, "version": 1}
        self.state = Path(request["state"])
        self.job_user = "eliza-slurm"

    def p(self, path):
        return self.root / path.lstrip("/")

    def managed(self, path: Path, data: str | bytes, mode=0o644):
        data = data.encode() if isinstance(data, str) else data
        if path.is_symlink():
            raise RuntimeError("Managed configuration is a symlink: " + str(path))
        if path.exists():
            current = hashlib.sha256(path.read_bytes()).hexdigest()
            recorded = self.receipt["files"].get(str(path))
            if current != recorded and path.read_bytes() != data:
                raise RuntimeError(f"Preserving changed/unmanaged file {path}; compare it with the installation receipt before retrying")
        atomic(path, data, mode)
        self.receipt["files"][str(path)] = hashlib.sha256(data).hexdigest()
        # Record each successful write so a later failure is resumable.
        atomic(self.receipt_path, json.dumps(self.receipt, indent=2).encode(), 0o600)

    def active(self, unit):
        result = run(["systemctl", "is-active", unit], check=False)
        if result.returncode not in (0, 3, 4):
            raise RuntimeError("Unable to inspect systemd service " + unit)
        return result.returncode == 0

    @contextmanager
    def lock(self):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        lock = self.state.with_suffix(".lock")
        with lock.open("a+") as handle:
            os.chown(self.state.parent, self.owner.pw_uid, self.owner.pw_gid)
            os.chown(lock, self.owner.pw_uid, self.owner.pw_gid)
            os.chmod(lock, 0o600)
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another host lifecycle operation is running") from exc
            yield

    def preflight(self, *, allow_active_munge=False):
        os_release = dict(line.split("=", 1) for line in self.p("/etc/os-release").read_text().splitlines() if "=" in line)
        if os_release.get("ID", "").strip('"') not in {"ubuntu", "debian"} or platform.machine() != "aarch64":
            raise RuntimeError("Automatic Slurm provisioning currently supports Ubuntu/Debian ARM64 DGX hosts")
        if not self.p("/run/systemd/system").exists() or not self.p("/sys/fs/cgroup/cgroup.controllers").exists():
            raise RuntimeError("A booted systemd host with cgroup v2 is required")
        if self.state.exists() and json.loads(self.state.read_text()).get("phase") != "inference":
            raise RuntimeError("Switch back to inference and resolve lifecycle errors before installing")
        for unit in UNITS:
            if self.active(unit) and not (allow_active_munge and unit == "munge.service"):
                raise RuntimeError(f"{unit} is active; provisioning will not interrupt/adopt a live scheduler")
            enabled = run(["systemctl", "is-enabled", unit], check=False).stdout.strip()
            if enabled in {"masked", "masked-runtime"}:
                raise RuntimeError(f"Preserving existing mask for {unit}; resolve it before provisioning")
        config = self.p("/etc/slurm/slurm.conf")
        if config.exists() and str(config) not in self.receipt["files"]:
            raise RuntimeError("An unmanaged Slurm configuration exists; preserve it and resolve ownership before provisioning")
        for name in ("slurmd", "slurmctld", "slurmrestd", "scontrol"):
            existing = shutil.which(name)
            if existing and not Path(existing).resolve().is_relative_to(self.prefix):
                raise RuntimeError(f"Unmanaged Slurm executable {existing}; do not mix it with the pinned installation")
        gpu = run(["nvidia-smi", "--query-gpu=index,driver_version", "--format=csv,noheader,nounits"]).stdout.strip().splitlines()
        if len(gpu) != 1:
            raise RuntimeError("This installation profile requires exactly one NVIDIA GPU")

    def packages(self):
        # Runtime masks prevent dpkg maintainer scripts from activating MUNGE.
        # Only remove masks this invocation created, including on install failure.
        created = []
        package_env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "l"}
        try:
            for unit in UNITS:
                mask = self.p("/run/systemd/system/" + unit)
                if not mask.exists() and not mask.is_symlink():
                    run(["systemctl", "mask", "--runtime", unit])
                    created.append(unit)
            run(["apt-get", "update"], env=package_env, capture=False)
            run(["apt-get", "install", "-y", "--no-install-recommends", *PACKAGES], env=package_env, capture=False)
            run(["systemctl", "disable", *UNITS], check=False)
        finally:
            for unit in created:
                run(["systemctl", "unmask", "--runtime", unit])

    def account(self, user, home=None):
        try:
            entry = pwd.getpwnam(user)
            if entry.pw_uid == 0:
                raise RuntimeError("Service account resolves to root: " + user)
        except KeyError:
            run(["useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin",
                 "--home-dir", home or "/nonexistent", user])

    def directory(self, path, owner, mode=0o750):
        path = self.p(path)
        path.mkdir(parents=True, exist_ok=True)
        run(["chown", owner, path])
        path.chmod(mode)

    def secret(self, path, owner, size=32, *, mode=0o640):
        path = self.p(path)
        if path.is_symlink():
            raise RuntimeError("Preserving symlinked credential: " + str(path))
        if not path.exists():
            atomic(path, secrets.token_bytes(size), mode)
        run(["chown", owner, path])
        path.chmod(mode)

    def slurm(self):
        complete = self.prefix / ".eliza-complete"
        if not complete.exists():
            archive = self.cache / f"slurm-{VERSION}.tar.bz2"
            download(f"https://download.schedmd.com/slurm/slurm-{VERSION}.tar.bz2", SLURM_SHA, archive)
            source = self.cache / f"slurm-{VERSION}"
            if not source.exists():
                with tarfile.open(archive) as tar:
                    tar.extractall(self.cache, filter="data")
            nvml = self.cache / "nvml"
            header = nvml / "include/nvml.h"
            candidates = sorted(self.p("/usr/local").glob("cuda*/include/nvml.h"))
            if candidates:
                atomic(header, candidates[-1].read_bytes())
            else:
                download(HEADER_URL, HEADER_SHA, header)
            libraries = [line.split()[-1] for line in run(["ldconfig", "-p"]).stdout.splitlines()
                         if "libnvidia-ml.so.1" in line and "aarch64" in line]
            if not libraries:
                # Some ldconfig implementations print libc6/AArch64 differently.
                libraries = [line.split()[-1] for line in run(["ldconfig", "-p"]).stdout.splitlines() if "libnvidia-ml.so.1" in line]
            if not libraries:
                raise RuntimeError("Existing NVIDIA NVML library was not found")
            stub = nvml / "lib64/stubs/libnvidia-ml.so"
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.unlink(missing_ok=True)
            stub.symlink_to(libraries[0])
            self.prefix.mkdir(parents=True, exist_ok=True)
            run([source / "configure", "--prefix=" + str(self.prefix), "--libdir=" + str(self.prefix / "lib"),
                 "--sysconfdir=" + str(self.p("/etc/slurm")), "--with-nvml=" + str(nvml), "--with-jwt=yes",
                 "--with-munge", "--enable-slurmrestd"], cwd=source, capture=False)
            run(["make", "-j", str(min(os.cpu_count() or 2, 4))], cwd=source, capture=False)
            run(["make", "install"], cwd=source, capture=False)
            self.verify_binaries()
            atomic(complete, (SLURM_SHA + "\n").encode())
        self.verify_binaries()
        for directory, names in (("bin", ("scontrol", "sinfo", "squeue", "sbatch", "srun", "scancel")),
                                 ("sbin", ("slurmd", "slurmctld", "slurmrestd"))):
            for name in names:
                link = self.p("/usr/local/" + directory + "/" + name)
                target = self.prefix / directory / name
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists() or link.is_symlink():
                    if link.resolve() != target:
                        raise RuntimeError("Preserving conflicting executable " + str(link))
                else:
                    link.symlink_to(target)

    def verify_binaries(self):
        version = run([self.prefix / "sbin/slurmd", "--version"]).stdout.strip()
        if version != "slurm " + VERSION:
            raise RuntimeError("Unexpected Slurm version: " + version)
        for plugin in PLUGINS:
            if not (self.prefix / "lib/slurm" / (plugin + ".so")).exists():
                raise RuntimeError("Required Slurm plugin missing: " + plugin)
        if not (self.prefix / "sbin/slurmrestd").exists():
            raise RuntimeError("Slurm REST executable is missing")

    def configuration(self):
        for user, home in (("slurm", None), ("slurmrest", None), (self.job_user, "/var/lib/slurm/jobs")):
            self.account(user, home)
        for path, owner, mode in (("/var/lib/slurm/slurmctld", "slurm:slurm", 0o750),
                                  ("/var/lib/slurm/slurmd", "root:root", 0o755),
                                  ("/var/log/slurm", "slurm:slurm", 0o750),
                                  ("/var/lib/slurm/jobs", "eliza-slurm:eliza-slurm", 0o750),
                                  ("/var/lib/slurm/jobs/logs", "eliza-slurm:eliza-slurm", 0o750)):
            self.directory(path, owner, mode)
        self.secret("/etc/slurm/jwt_hs256.key", "root:slurm")
        # Unlike the Slurm JWT key, munged rejects group-readable key files.
        self.secret("/etc/munge/munge.key", "munge:munge", size=1024, mode=0o600)
        node = platform.node().split(".")[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", node):
            raise RuntimeError("Unsupported node hostname")
        discovered = topology(run([self.prefix / "sbin/slurmd", "-C"]).stdout, self.request["reserve_mb"])
        fields = " ".join(f"{key}={value}" for key, value in discovered.items())
        config = f"""# Managed by eliza-control installer; receipt detects local edits.
ClusterName=eliza-training
SlurmctldHost={node}
SlurmUser=slurm
AuthType=auth/munge
AuthAltTypes=auth/jwt
AuthAltParameters=jwt_key=/etc/slurm/jwt_hs256.key
PluginDir={self.prefix}/lib/slurm
StateSaveLocation=/var/lib/slurm/slurmctld
SlurmdSpoolDir=/var/lib/slurm/slurmd
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdLogFile=/var/log/slurm/slurmd.log
SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory
SchedulerType=sched/backfill
GresTypes=gpu
ProctrackType=proctrack/cgroup
TaskPlugin=task/cgroup,task/affinity
ReturnToService=2
JobCompType=jobcomp/filetxt
JobCompLoc=/var/log/slurm/completed-jobs.log
JobRequeue=0
NodeName={node} {fields} Gres=gpu:1 State=UNKNOWN
PartitionName=training Nodes={node} Default=YES State=INACTIVE OverSubscribe=EXCLUSIVE AllowGroups=eliza-slurm DefaultTime=60 MaxTime=1440 DefMemPerNode=16384 MaxMemPerNode={discovered['RealMemory']}
"""
        self.managed(self.p("/etc/slurm/slurm.conf"), config)
        self.managed(self.p("/etc/slurm/gres.conf"), "AutoDetect=nvml\n")
        self.managed(self.p("/etc/slurm/cgroup.conf"), "CgroupPlugin=cgroup/v2\nConstrainCores=yes\nConstrainRAMSpace=yes\nConstrainDevices=yes\n")
        for unit, user, args in (("slurmctld", "slurm", "-D"), ("slurmd", "root", "-D"),
                                  ("slurmrestd", "slurmrest", "-a rest_auth/jwt -s openapi/slurmctld 0.0.0.0:6820")):
            extras = "Environment=SLURM_JWT=daemon\n" if unit == "slurmrestd" else ""
            extras += "Delegate=yes\n" if unit == "slurmd" else ""
            self.managed(self.p("/etc/systemd/system/" + unit + ".service"),
                         f"[Unit]\nDescription=Eliza on-demand {unit}\nAfter=network-online.target munge.service\nRequires=munge.service\n\n[Service]\nType=simple\nUser={user}\n{extras}ExecStart={self.prefix}/sbin/{unit} {args}\nRestart=on-failure\nRestartSec=5\n")
        host = {"slurm_prefix": str(self.prefix), "job_user": self.job_user,
                "control_user": self.owner.pw_name, "state": str(self.state), "node": node, "token_lifespan": 3600,
                "rest_url": self.request["slurm_url"], "api_versions": ["v0.0.45"], "workspace": "/var/lib/slurm/jobs",
                "partitions": [{"name": "training", "gpu_resource": "gres/gpu:1", "gpus": 1,
                                "cpus": discovered["CPUs"], "memory_mb": discovered["RealMemory"], "max_time_minutes": 1440}]}
        self.managed(self.p("/etc/eliza-slurm/host.json"), json.dumps(host, indent=2))
        self.managed(self.p("/usr/local/sbin/eliza-slurm-admin"), (self.repo / "scripts/lib/slurm_admin.py").read_bytes(), 0o755)
        policy = f"{self.owner.pw_name} ALL=(root) NOPASSWD: /usr/local/sbin/eliza-slurm-admin\n"
        # Validate before publishing privileges.
        temporary = self.cache / "sudoers.check"
        atomic(temporary, policy.encode(), 0o440)
        run(["visudo", "-cf", temporary])
        self.managed(self.p("/etc/sudoers.d/eliza-slurm-control"), policy, 0o440)
        self.receipt.update(node=node, resources=discovered, slurm_version=VERSION)

    def verify_api(self):
        result = run(["runuser", "-u", "slurmrest", "--", "env", "SLURM_JWT=daemon",
                      self.prefix / "sbin/slurmrestd", "-s", "openapi/slurmctld", "-d", "v0.0.45", "--generate-openapi-spec"])
        schema = json.loads(result.stdout)
        if "/slurm/v0.0.45/job/submit" not in schema.get("paths", {}):
            raise RuntimeError("Installed REST API does not export the required v0.0.45 submission route")

    @contextmanager
    def verification_auth(self):
        unit = "munge.service"
        temporary = not self.active(unit)
        try:
            if temporary:
                try:
                    run(["systemctl", "start", unit])
                except RuntimeError as exc:
                    raise RuntimeError(f"{exc}\nFor MUNGE startup details, run: sudo journalctl -u munge.service -b -n 40 --no-pager") from exc
            deadline = time.monotonic() + 10
            while True:
                try:
                    probe = run(["munge", "-n"], check=False, timeout=2)
                    if probe.returncode == 0:
                        break
                    detail = probe.stderr.strip()
                except subprocess.TimeoutExpired:
                    detail = "credential probe timed out"
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"MUNGE authentication did not become ready: {detail}")
                time.sleep(0.25)
            yield
        finally:
            if temporary:
                run(["systemctl", "stop", unit])

    def verify_scheduler_config(self):
        with self.verification_auth():
            result = run([self.prefix / "sbin/slurmd", "-G"])
            if "gpu" not in (result.stdout + result.stderr).lower():
                raise RuntimeError("slurmd -G did not report the GPU; inspect NVML/topology before activation")
            self.verify_api()

    def check(self):
        with self.lock():
            self.preflight(allow_active_munge=True)
            self.verify_binaries()
            self.verify_scheduler_config()
            if not self.receipt.get("complete"):
                raise RuntimeError("Installation receipt is incomplete; rerun the installer")
            report = {key: self.receipt.get(key) for key in
                      ("complete", "slurm_version", "node", "resources")}
            report.update(scheduler_state="stopped", api="v0.0.45")
            print(json.dumps(report, indent=2))

    def apply(self):
        with self.lock():
            self.preflight()
            self.receipt.update(complete=False)
            atomic(self.receipt_path, json.dumps(self.receipt, indent=2).encode(), 0o600)
            self.cache.mkdir(parents=True, exist_ok=True)
            self.packages()
            self.slurm()
            self.configuration()
            self.verify_scheduler_config()
            run(["systemctl", "daemon-reload"])
            for unit in UNITS:
                if self.active(unit):
                    raise RuntimeError("A scheduler service was activated during installation: " + unit)
                enabled = run(["systemctl", "is-enabled", unit], check=False).stdout.strip()
                if enabled not in {"disabled", "static"}:
                    raise RuntimeError(f"{unit} is unexpectedly boot-enabled or masked: {enabled}")
            # A configuration lock shared with inference startups; do not change its mode.
            if not self.state.exists():
                atomic(self.state, b'{"version":1,"phase":"inference","restore":[]}', 0o600)
            os.chown(self.state, self.owner.pw_uid, self.owner.pw_gid)
            run(["loginctl", "enable-linger", self.owner.pw_name])
            self.receipt.update(complete=True)
            for retired in ("training_package", "training_profile", "storage_configured"):
                self.receipt.pop(retired, None)
            atomic(self.receipt_path, json.dumps(self.receipt, indent=2).encode(), 0o600)


def configuration_request(args, repo: Path):
    owner = pwd.getpwuid(os.getuid())
    if owner.pw_uid == 0:
        raise RuntimeError("Run install-control-daemon without sudo; it requests sudo for the host stage")
    state = os.environ.get("ELIZA_ENVIRONMENT_STATE")
    if not state:
        legacy = repo / ".runtime/environment.json"
        state = str(legacy if legacy.exists() else Path(owner.pw_dir) / ".local/state/eliza/environment.json")
    state = str(Path(state).expanduser().resolve())
    url = args.slurm_url or os.environ.get("ELIZA_SLURM_PUBLIC_URL") or "http://" + platform.node().split(".")[0] + ":6820"
    if urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).hostname:
        raise RuntimeError("Slurm advertisement URL must be HTTP(S)")
    return {"repo": str(repo), "owner": owner.pw_name, "state": state, "reserve_mb": args.reserve_memory_mb,
            "slurm_url": url, "check": args.check}


def install_control(repo: Path, request: dict):
    runtime = repo / ".runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    python = repo / ".venvs/control/bin/python"
    if not python.exists():
        run([sys.executable, "-m", "venv", python.parent.parent], capture=False)
    run([python, "-m", "pip", "install", "-r", repo / "services/control_daemon/requirements.txt"], capture=False)
    run([python, "-m", "pip", "check"], capture=False)
    token = os.environ.get("CONTROL_DAEMON_TOKEN")
    if not token and os.environ.get("CONTROL_DAEMON_TOKEN_FILE"):
        token = Path(os.environ["CONTROL_DAEMON_TOKEN_FILE"]).read_text().strip()
    token_file = runtime / "control-token"
    if not token_file.exists():
        atomic(token_file, (token or secrets.token_urlsafe(32)).encode(), 0o600)
    token_file.chmod(0o600)
    settings = {"CONTROL_DAEMON_PYTHON": str(python), "CONTROL_DAEMON_TOKEN_FILE": str(token_file),
                "ELIZA_TRAINING_ENABLED": "true", "ELIZA_ENVIRONMENT_STATE": request["state"],
                "ELIZA_SLURM_ADMIN_PREFIX": "sudo -n /usr/local/sbin/eliza-slurm-admin",
                "ELIZA_SLURM_PARTITION": "training", "ELIZA_SLURM_NODE": platform.node().split(".")[0],
                "ELIZA_SLURM_REST_URL": "http://127.0.0.1:6820",
                "ELIZA_SLURM_USER": "eliza-slurm", "ELIZA_SLURM_TOKEN_LIFESPAN": "3600"}
    atomic(runtime / "control-install.env", "".join(f"{key}={shlex.quote(value)}\n" for key, value in settings.items()).encode(), 0o600)
    unit = Path.home() / ".config/systemd/user/eliza-control-daemon.service"
    working = json.dumps(str(repo).replace("%", "%%"))
    start = json.dumps(str(repo / "services/control-daemon/start.sh").replace("%", "%%"))
    text = f"[Unit]\nDescription=Eliza host control daemon\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory={working}\nExecStart={start}\nRestart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n"
    if unit.exists() and not ("Eliza Inference REST Control Daemon" in unit.read_text() or "Eliza host control daemon" in unit.read_text()):
        raise RuntimeError("Preserving an unrecognized existing control systemd unit: " + str(unit))
    if unit.exists() and not unit.with_suffix(".service.pre-install").exists():
        atomic(unit.with_suffix(".service.pre-install"), unit.read_bytes())
    atomic(unit, text.encode())
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "eliza-control-daemon.service"])
    run(["systemctl", "--user", "restart", "eliza-control-daemon.service"])
    host = os.environ.get("HOST", "127.0.0.1")
    host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    deadline = time.monotonic() + 30
    while True:
        try:
            with urlopen(f"http://{host}:{os.environ.get('PORT', '8030')}/health", timeout=2) as response:
                if json.loads(response.read(4096)).get("service") != "control-daemon":
                    raise RuntimeError("Unexpected service on the control port")
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("Control daemon health check failed; inspect systemctl --user status eliza-control-daemon.service")
            time.sleep(1)
    print("Control daemon installed. Slurm is provisioned and stopped; inference mode is preserved.")
    print("Control token file for Jupyter: " + str(token_file))
    print("Next: ./scripts/environment advertise; submit your own batch job after switching to training mode.")


def main():
    parser = argparse.ArgumentParser(description="Install control daemon and on-demand Slurm on an ARM64 DGX.")
    parser.add_argument("--plan", action="store_true", help="Print installation steps without changes or prompts")
    parser.add_argument("--check", action="store_true", help="Verify in inference mode; only MUNGE may start temporarily")
    parser.add_argument("--root-stage", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--slurm-url", help="Advertised REST URL reachable from submitting clients")
    parser.add_argument("--reserve-memory-mb", type=int, default=8192)
    args = parser.parse_args()
    if args.reserve_memory_mb < 1024:
        parser.error("reserve-memory-mb must be at least 1024")
    repo = Path(__file__).resolve().parents[2]
    try:
        if args.plan:
            print(json.dumps({"slurm_version": VERSION, "api": "v0.0.45", "packages": PACKAGES,
                              "steps": ["host preflight", "masked package setup", "verified Slurm build", "accounts/configuration/keys/permissions", "GPU and API checks with temporary MUNGE", "control daemon activation"],
                              "scheduler_final_state": "stopped"}, indent=2))
            return 0
        if args.root_stage:
            if os.getuid() != 0:
                raise RuntimeError("Host stage requires sudo")
            request = json.load(sys.stdin)
            os.umask(0o022)
            provisioner = Provisioner(request)
            provisioner.check() if request.get("check") else provisioner.apply()
        else:
            request = configuration_request(args, repo)
            # Secrets travel over stdin, not command-line arguments or logs.
            result = subprocess.run(["sudo", *(["-n"] if args.non_interactive else []), sys.executable, str(Path(__file__).resolve()), "--root-stage"],
                                    input=json.dumps(request), text=True)
            if result.returncode:
                raise RuntimeError("Host provisioning failed; fix the reported step and rerun the same installer")
            if not args.check:
                install_control(repo, request)
        return 0
    except Exception as exc:
        print("Installation failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
