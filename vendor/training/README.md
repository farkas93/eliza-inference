# Standalone training runner

`run_bundle.py` is vendored byte-for-byte from `eliza-spark` commit
`78f61af8669bf0e5b24d5c1f5a252c0a88a9cec5`, path `slurm/run_bundle.py`.
SHA-256: `b7f6993030eebeec5d3016a3a39d99d6cd33ea1b41bcdd376ac74c246b4b7959`.

The host installer checks this digest before copying the worker into its isolated
training installation. Updating the protocol/worker requires updating the pinned
source provenance and installer checksum together, plus the submission/worker
round-trip tests. The inference/control process never imports this worker.
