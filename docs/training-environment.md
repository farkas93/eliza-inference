# On-demand DGX training environment

The existing control daemon remains running in both modes. Model servers and
Slurm are mutually exclusive. The daemon and this lifecycle module need no
PyTorch, TRL, Spark or training-package dependencies.

## Host provisioning

Install the control daemon and native Slurm automatically:

```bash
./scripts/setup control --plan
./scripts/setup control
./scripts/setup control --check
```

See [the executable installation and acceptance guide](control-installation.md).
The installer generates the settings/permissions described below and leaves Slurm
stopped. The following details document the installed boundary and advanced
deployment configuration; manual Slurm assembly is no longer the default path.

The installed environment uses **single-node Slurm**, following the infrastructure
runbook in `eliza-spark/docs/setup/dgx-slurm.md`. The service names are
`munge.service`, `slurmctld.service`, `slurmd.service`, `slurmrestd.service`.
They must be installed but **disabled at boot**, not enabled by another target.
Configure persistent Slurm state/spool directories, a partition named `training`,
and one explicitly discovered GPU. Verify ARM64/GB10 support, NVML and cgroups on
the actual DGX. Do not replace its installed NVIDIA driver blindly.

Configure `.env`:

```bash
ELIZA_TRAINING_ENABLED=true
ELIZA_ENVIRONMENT_STATE="$HOME/.local/state/eliza/environment.json"
ELIZA_SLURM_NODE=dgx-spark       # exact Slurm NodeName
ELIZA_SLURM_PARTITION=training
ELIZA_SLURM_ADMIN_PREFIX="sudo -n"
CONTROL_DAEMON_TOKEN="<your control token>"
```

The control account needs permission for these exact administrative operations:

- `systemctl start|stop` for the four training units above;
- `scontrol update PartitionName=training State=UP|INACTIVE`.
- `scontrol token username=<ELIZA_SLURM_USER> lifespan=<ELIZA_SLURM_TOKEN_LIFESPAN>`
  for the configured non-root scheduler job account (defaults `eliza-slurm`, 3600).

Use a host-admin-installed narrowly scoped sudoers policy, with absolute command
paths resolved on that host. Do not grant arbitrary shell or wildcard scontrol
access. Read-only `systemctl`, `scontrol ping`, `sinfo`, `squeue` must also work
for the control account (MUNGE identity configured during training).
`ELIZA_SLURM_ADMIN_PREFIX` may be empty if a deployment supplies equivalent
privileges through another host service boundary.

The explicit host installer installs packages and host permissions. Application
verification tests do not install packages or activate live services.

## Operator interface

```bash
./scripts/environment status
./scripts/environment training
# Submit/watch jobs through Slurm; training stays active between jobs.
./scripts/environment inference
```

REST equivalents, authenticated using the existing control token:

- `GET /environment` — persisted mode/transition/error/restore state;
- `POST /environment/training` — switch, verify readiness, open submission;
- `POST /environment/inference` — close submission, check jobs, stop training,
  restore previous inference profiles and run their smoke checks.
- `POST /training/token` — delegate a short-lived Slurm JWT for the configured
  training account only, while training is ready. This route requires a configured
  control token even when legacy lifecycle routes allow trusted-LAN access. No
  caller-supplied username or lifetime is accepted. The notebook client caches and
  refreshes the credential without displaying or persisting it in run artifacts.

`GET /slurm` advertises scheduler capabilities and readiness; `POST /slurm/token`
is the canonical credential endpoint. The host has no trainer/package/profile
selection API. A submitted batch job owns its execution runtime and dependencies.

`GET /environment` reports persisted lifecycle state, not a live health check.
Posting the current mode rechecks readiness. A busy switch returns HTTP 409;
an operational failure returns 500 and leaves persisted `failed` state. The
existing `/stack/start` and `/service/.../start` operations remain inference-only;
they do not implicitly switch the host out of training.

## Exclusion and recovery

The controller saves the exact profiles of **running** managed tmux services,
stops corresponding active user-systemd units and service supervisors, then
checks that managed sessions and NVIDIA compute processes have disappeared.
Unknown live profiles block the transition before shutdown. Independent GPU
processes block handover rather than being killed.

A file lock serializes transitions and holds through `scripts/start`, including
CLI and user-systemd starts. Restoration inherits the lock descriptor. Failed
or transitional states block new inference starts. Supported service starts
must use `scripts/start`; calling backend entrypoints directly bypasses lifecycle
management. Do not configure independent boot/restart mechanisms for Slurm.

Before switching back, the controller makes the training partition INACTIVE
(rejects new submissions and halts scheduling), stops REST, and inspects **all**
pending/running/completing jobs. If jobs remain, it reopens training and returns
409. Finish them or explicitly cancel via Slurm, then retry; switching never
implicitly cancels work. All job submissions must target the single `training`
partition; do not add alternative partitions which bypass this boundary.

The original restore snapshot survives failures and control-daemon restarts.
After inspecting the persisted error and actual host state, retry the desired
mode. A partial training startup can be recovered by switching to inference.
Do not delete the state file to clear an error: that loses the restore snapshot
and can permit overlapping environments.

Inference restoration uses the saved profiles through `scripts/start` rather
than reactivating systemd units with possibly different hard-coded profiles.
The lifecycle controller owns those restored tmux services. User-unit enablement
is not changed; boot-time inference starts respect the persisted mode guard.
Store environment state on persistent host storage shared by all supported
control entrypoints, not under a disposable container filesystem.

Run manifests, archived logs and checkpoints are independent of Slurm's
availability. Notebook monitoring can reconnect while training is active and
read archived outcomes after Slurm is stopped. Do not infer successful training
from a scheduler service shutdown or a missing job record.
