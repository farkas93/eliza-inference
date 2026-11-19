# Install host control and advertise Slurm

Run on the DGX as your normal control/inference user:

```bash
./scripts/setup control --plan
./scripts/setup control
./scripts/setup control --check
```

The existing `scripts/installation-suite/install-control-daemon` entrypoint is
equivalent. It requests sudo for native host provisioning.

## Authority

This installer owns **Slurm and inference/Slurm GPU handover only**. It installs
native Slurm 26.05.6, MUNGE/JWT, GPU discovery/cgroups, service accounts, scheduler
state/log/job directories, an allowlisted control helper and the thin control
daemon's environment. It neither fetches `nlp-lab` nor chooses/installs training
frameworks, Python training environments, workers, models or dataset/storage settings.

The scheduler services stay stopped and disabled/static during inference. The
control daemon remains available across SSH logout through user lingering.
Inference and Slurm-enabled modes are mutually exclusive; this concerns GPU
ownership, not a particular training runtime.

The supported host is Ubuntu/Debian ARM64 with systemd, cgroup v2 and one NVIDIA
GPU. The installer reuses the existing NVIDIA driver and discovers CPU/RAM/GPU
resources. Node memory reserves the greater of 8 GiB or 10% for the host; change
the floor with `--reserve-memory-mb`. Runtime/driver compatibility is the job
submitter's responsibility.

## Advertisement and access

Set a scheduler URL reachable from Jupyter, when automatic hostname discovery
does not resolve from the pod:

```bash
./scripts/setup control --slurm-url http://<DGX-address>:6820
```

Alternatively set `ELIZA_SLURM_PUBLIC_URL` in the operator environment. The
installer writes `/etc/eliza-slurm/host.json` with scheduler capabilities.

```bash
./scripts/environment advertise
./scripts/environment training
```

Authenticated API:

- `GET /slurm`: REST URL, validated API versions, partitions/GPU/CPU/memory/time
  limits, job workspace/account, current mode and readiness;
- `POST /slurm/token`: scoped scheduler credential for the configured non-root
  job account; `/training/token` remains a compatibility alias;
- `POST /environment/training`: release inference and enable Slurm;
- `POST /environment/inference`: reject new submissions, require the queue to
  drain, stop Slurm and restore previous inference profiles.

Advertisement remains available while Slurm is stopped, with `ready: false`.
There is no training package revision, runtime profile or interpreter in it.
The generic job account is `eliza-slurm`, with a writable workspace at
`/var/lib/slurm/jobs` and scheduler stdout/stderr directory `logs/`.

The generated control token is at `.runtime/control-token` (0600). Transfer it
through your secret-management mechanism to Jupyter as `CONTROL_DAEMON_TOKEN_FILE`.
Configure `INFERENCE_CONTROL_URL` for the host API. A submitter can use the
advertised REST URL or supply its own reachable `SLURM_REST_URL` override.

## Jobs own their execution environment

Install/use `nlp-lab`'s lightweight client in the notebook. It selects runtime
code, dependencies, model/config/data, storage access and resource requests, then
submits a normal Slurm batch script. Any environment preparation runs **inside
that allocation under the job user**, without host-installer authority.

The client carries its bootstrap/runtime package with the job. No training
package needs to exist on the DGX before submission. Dataset jobs can fetch a
checksum-pinned bundle using a limited-lifetime signed URL; probes can carry
their small bundle inline. The OS Python used by the batch entrypoint is part
of the host platform, not a host-selected model-training environment.

See `nlp-lab/docs/runs/jupyter-slurm-training.md` for job submission and probes.
After your jobs finish:

```bash
./scripts/environment inference
```

A busy transition preserves Slurm mode and reports pending/running jobs. It never
implicitly cancels work. The control daemon stays up in both modes.

## Verification, reruns and migration

Installation and `--check` verify GPU discovery and the generated REST schema
while in inference mode. Slurm's GPU probe requires MUNGE authentication, so
the installer starts only `munge.service` for verification if it is stopped,
waits for a credential probe to succeed, and stops it afterward even if a check
fails. `--check` leaves an already-running MUNGE service alone. The Slurm
controller, compute daemon and REST service stay stopped throughout. Runtime
compatibility and a real GPU job require a separate submitter-owned test.

The installation receipt records native managed files and completion. Reruns
reuse verified binaries and preserve existing keys/state. Changed/unmanaged files
are reported before replacement. Runtime masks prevent package scripts from
activating scheduler services during install and are unwound on failure.

On upgrade from the previous combined installer, run `./scripts/setup control`
again. It updates the scheduler job account/advertisement and retires runtime
selection from the receipt. Existing training environments, storage files and
caches are left as user-managed assets; the host no longer consumes them.

Useful diagnostics:

```bash
systemctl --user status eliza-control-daemon.service
sudo journalctl -u munge.service -b -n 40 --no-pager
sudo journalctl -u slurmctld.service -u slurmd.service -u slurmrestd.service
```

If MUNGE rejects a group-readable key from an earlier installation, rerun
`./scripts/setup control` before `--check`. Setup corrects the key's ownership
and permissions (`munge:munge`, `0600`) without replacing the key.
