# Install host control and on-demand training

Run on the **DGX host**, from the updated `eliza-inference` checkout, as your
normal inference/control user. The installer requests sudo for its host stage.

```bash
./scripts/setup control --plan     # inspect the steps; no installation or prompts
./scripts/setup control            # install control + Slurm + isolated TRL runtime
./scripts/setup control --check    # verify the installed host while in inference mode
```

The original entrypoint is equivalent:

```bash
./scripts/installation-suite/install-control-daemon
```

**You do not need to install or configure Slurm manually first.** The installer
prepares it and keeps it stopped. Installing the daemon does not switch the
GPU away from inference. Stop/drain an already active scheduler and return to
inference mode before rerunning provisioning.

## What the command installs

- Native build/authentication/cgroup dependencies through apt, including MUNGE.
- Checksum-pinned **Slurm 26.05.6** under `/opt/eliza-slurm/26.05.6`, with REST
  API `v0.0.45`, JWT, NVML, and cgroup-v2 support. The first run builds from the
  official SchedMD release; subsequent runs reuse the completed installation.
- One discovered CPU/GPU node and one `training` partition. Memory headroom is
  the greater of 8 GiB or 10% of reported host RAM. Override the floor with
  `--reserve-memory-mb <MiB>`. The installer validates the discovered topology
  rather than assuming an x86 or homogeneous ARM CPU layout.
- Service accounts, persistent state/log/run directories, authentication keys,
  and a root-owned, allowlisted administrative helper for the control account.
- Independent bootstrap and **CPython 3.12 TRL training environments** under
  `/opt/eliza-training`. The training profile pins a PyTorch CUDA 13 ARM64 wheel.
  It requires the existing NVIDIA driver to be 580 or newer. The installer does
  not upgrade the NVIDIA driver or inference's Python environments.
- The pinned standalone run-bundle worker, shipped inside this repository.
  A separate private `eliza-spark` checkout/download is not required.
- A control-only environment at `.venvs/control`, a persistent control-token
  file, and the user systemd control service. Startup uses the prepared Python
  environment and checks `/health`. User lingering is enabled so the control
  service can start at boot and remain available after SSH logout.

Root Slurm units have no boot enablement. Runtime masks prevent package
maintainer scripts from starting services during dependency installation. Masks
created by the installer are removed on success/failure; pre-existing masks are
preserved. Final verification requires the scheduler services to be stopped
and disabled/static. The control daemon is the component left running.

The supported automatic host profile is Ubuntu/Debian **ARM64**, booted with
systemd and cgroup v2, with exactly one NVIDIA GPU. Unsupported configurations
fail preflight rather than receiving guessed configuration.

## Storage and credentials

The installer reads `STORAGE_URL`, `STORAGE_ACCOUNT`, `STORAGE_KEY` (or the
`*_FILE` credential variants) from the operator's environment/`.env`. If settings
are missing on an interactive terminal, it prompts for the endpoint and hidden
credentials. Leave the endpoint empty to finish control/GPU infrastructure
setup first; dataset jobs will still need storage configured.

For automation, provide those settings and use:

```bash
./scripts/setup control --non-interactive
```

Credentials go to protected files under `/etc/eliza-training/`, readable by the
training account, and are passed to the host installer through stdin rather
than command-line arguments. Do not commit `.env` or credential files. The
MLflow URL comes from `MLFLOW_TRACKING_URI`, defaulting to the homelab endpoint.
Site-specific MLflow/HF access credentials can be added to the protected runtime
environment before the corresponding experiment.

Generated host-control settings live in `.runtime/control-install.env` and take
precedence over old control/Slurm defaults in `.env`. Your inference profiles and
backend settings continue to come from their normal configuration. The installer
preserves an existing control token, or creates `.runtime/control-token` with
mode 0600. Transfer that credential using your secret-management mechanism into
Jupyter as `CONTROL_DAEMON_TOKEN_FILE`; do not print it in a notebook.

Configure Jupyter with:

```text
INFERENCE_CONTROL_URL=http://<DGX-address>:8030
SLURM_REST_URL=http://<DGX-address>:6820
CONTROL_DAEMON_TOKEN_FILE=<mounted-control-secret-file>
```

The client obtains/refreshes a JWT for the fixed `eliza-training` account through
the authenticated control API. No manual Slurm token command is required.

To prepare only scheduler/bootstrap infrastructure and defer GPU libraries:

```bash
./scripts/setup control --training-profile bootstrap
# Later, install the default TRL training profile:
./scripts/setup control --training-profile trl
```

The bootstrap profile is not ready for the GPU probe/model training until the
TRL profile has been installed. No models or datasets are downloaded by setup.

## First acceptance test

After setup, first inspect the offline installation check in inference mode:

```bash
./scripts/setup control --check
./scripts/environment status
```

`--check` validates binaries, generated REST schema and GPU discovery without
starting Slurm. Its report distinguishes configured storage from deferred storage.

Then explicitly hand over the GPU and submit the small probe:

```bash
./scripts/environment training
./scripts/training-smoke
```

The probe uses the control API/JWT and Slurm REST, performs a small CUDA
forward/backward operation, verifies finite loss/gradients, and saves `probe.pt`.
It requires no HASS dataset or MinIO credentials. It prints a probe UUID and
Slurm job ID; logs and artifacts live under `/var/lib/eliza-training/runs/`.
Use your host-admin access to inspect those local files.

In another terminal while the probe is holding its CUDA allocation:

```bash
./scripts/environment inference
```

Expected: a busy error and continued training mode. The probe holds for 30 seconds
by default; `./scripts/training-smoke --hold-seconds 120` gives more time to test.
After the job completes:

```bash
./scripts/environment inference
```

Expected: all Slurm/MUNGE services stop and the previously active inference
profiles are restored and pass their smoke checks. The control service stays up.
Do not resubmit a probe automatically after an ambiguous HTTP timeout: inspect
its printed UUID/job ID and scheduler records first.

Useful diagnostics:

```bash
systemctl --user status eliza-control-daemon.service
sudo journalctl -u slurmctld.service -u slurmd.service -u slurmrestd.service
```

Actual HASS training additionally requires a frozen SFT release, a private
config, and the trainer fidelity fixes described in the HASS training plan.
The GPU probe tests infrastructure, not the correctness of the training corpus.

## Reruns and recovery

The host receipt `/var/lib/eliza-control-install/receipt.json` records successful
managed file writes and completion. A failed build/setup can be retried with the
same command. Source archives and completed binaries are reused after checksum
and plugin checks. Existing JWT/MUNGE keys, control credentials and scheduler state
are preserved. No state-reset flags are passed to Slurm.

Changed/unmanaged scheduler configuration or executable paths stop installation
with their exact path; resolve the ownership/configuration conflict deliberately.
Do not delete a live scheduler's state or overwrite its configuration to bypass
this check. Runtime environment values are preserved; missing installer settings
can be appended to an unmodified managed file. If you edited that file manually,
add any missing storage settings there explicitly rather than losing your edits.
An original recognized control systemd unit is backed up once before replacement.

Build/dependency verification in the development workspace uses simulated host
commands. A real DGX installation and GPU smoke run are still required for host
acceptance; repository tests do not establish live GPU compatibility.
