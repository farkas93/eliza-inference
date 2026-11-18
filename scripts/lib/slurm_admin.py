#!/usr/bin/python3
"""Root-owned, allowlisted adapter for the host-control account's sudo access."""
import json
import os
import subprocess
import sys
from pathlib import Path

UNITS = {"munge.service", "slurmctld.service", "slurmd.service", "slurmrestd.service"}


def command(args, config):
    prefix = Path(config["slurm_prefix"])
    if len(args) == 3 and args[0] == "systemctl" and args[1] in {"start", "stop"} and args[2] in UNITS:
        return ["/usr/bin/systemctl", *args[1:]]
    if args in (["scontrol", "update", "PartitionName=training", "State=UP"],
                ["scontrol", "update", "PartitionName=training", "State=INACTIVE"]):
        return [str(prefix / "bin/scontrol"), *args[1:]]
    expected = ["scontrol", "token", "username=" + config["training_user"],
                "lifespan=" + str(config["token_lifespan"])]
    if args == expected:
        return [str(prefix / "bin/scontrol"), *args[1:]]
    raise ValueError("Operation is outside the installed Slurm allowlist")


def main():
    if os.getuid() != 0:
        raise PermissionError("This helper requires sudo")
    config = json.loads(Path("/etc/eliza-training/host.json").read_text())
    if os.environ.get("SUDO_USER") != config["control_user"]:
        raise PermissionError("Caller is not the configured control account")
    args = sys.argv[1:]
    cmd = command(args, config)
    state = json.loads(Path(config["state"]).read_text())
    phase = state["phase"]
    if args[0] == "systemctl" and args[1] == "start" and phase not in {"training", "switching_to_training", "switching_to_inference"}:
        raise PermissionError("Slurm activation is outside a managed environment transition")
    if args[:2] == ["scontrol", "token"] and phase != "training":
        raise PermissionError("Training credentials require training mode")
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}
    return subprocess.run(cmd, env=env, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
