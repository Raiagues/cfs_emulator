# Shared-profile compilation measurements

This dataset measures ten incremental compilation cycles for the artifacts used by both QEMU and the physical Raspberry Pi. The compiler runs on the host in the existing builder image. App creation and deletion also run on the host. These records do not represent guest execution, board execution, or two independent builds for those targets.

The mission uses platform commit `64add2472dbf6869563612cf6b2c427b181dba5d` and the official NASA checkout identified in `prepare.json`. The measurement procedure is frozen at `f6beb5f00ebff836ea9d6b8051f18db7df461050` and the independent analysis at `fbf5390568f7be657d6cb80befcad85a1f1274a7`; its source hashes are in `analysis/summary.json`. Preparation made an independent copy of a verified clean official checkout and generated a new mission through the public CLI. No mission or build artifacts from the earlier dataset were copied.

## Procedure and boundaries

1. Prepare a new independent mission, with no existing flight build.
2. Build the ARM baseline once. Record this prerequisite separately, outside the incremental series.
3. Repeat ten times: create `eval_cycle_NN`, compile with `build --target qemu`, and delete that app. Time every complete CLI operation, preserving all observations.
4. Recompile after removing the cycle apps, outside the ten cycles. Compare the input manifests and verify the restored app membership, startup, schedules and telemetry subscriptions.
5. Derive per-operation statistics with inclusive quartiles. All compilation uses one worker. No QEMU boot or SSH operation is part of this procedure.

The shared profile is selected through the QEMU CLI target. The [mission evaluation](../final/README.md) separately verifies identical artifacts installed on QEMU and the physical board. The additional compilation series makes no new claim about runtime or physical sensor behavior.

## Evidence

| File | Content |
| --- | --- |
| [analysis/summary.json](analysis/summary.json) | Final status, product and procedure revisions, host, table hashes and sample counts |
| [analysis/q5_statistics.csv](analysis/q5_statistics.csv) | Three operation summaries: creation, incremental compilation and deletion |
| [analysis/q5_timings.csv](analysis/q5_timings.csv) | Thirty individual durations, without filtering slow observations |
| [cycles/metrics.json](cycles/metrics.json) | Cycle order, prerequisite build and restoration build |
| [cycles/commands.json](cycles/commands.json) | Exact commands, timestamps, exit codes, stdout and stderr log names |
| [cycles/sources-before-cycles.json](cycles/sources-before-cycles.json) and [cycles/sources-after-cycles.json](cycles/sources-after-cycles.json) | Before/after input manifests and per-file hashes |
| [prepare.json](prepare.json) and [prepare/commands.json](prepare/commands.json) | Mission preparation, official source identity and public CLI steps |
| [analysis/source-audit.json](analysis/source-audit.json) | Generated integration changes, before/after source references and eight equivalent preprocessed tables |
| [preconditions.json](preconditions.json) | Sequential execution, one-worker limit and existing builder image identity |
| [preparation-audit.json](preparation-audit.json) | Cross-check of the original QEMU image preparation and first-provisioning durations |
| [SHA256SUMS](SHA256SUMS) | Integrity of this published evidence package |

The numbered files under `cycles/` preserve stdout/stderr and the inputs captured before each build. Membership management materializes six generated integration files; the source audit verifies the restored mission membership and the equivalence of its generated tables. The source trees are not byte-identical. The original strict byte-comparison record remains unchanged, and the separate verification report determines whether the completed timing observations are publishable. The host is not a controlled performance laboratory; statistics describe these operations and conditions without inferring a performance improvement.

## Reproduce

Use the commands in the [validation guide](../../README.md#incremental-builds-for-the-shared-qemuphysical-profile) with a new workspace and output directory. The [measurement procedure](../../compilation.py) refuses existing ARM build artifacts and an uncommitted measurement script. The [independent verifier](../../compilation_summary.py) validates the complete operation sequence and the generated integration files. Small generated mission-table snapshots are retained as evidence; expanded NASA headers and the cloned cFS tree are not published. The original final campaign remains unchanged under `validation/results/final/`.

To verify this package from its directory:

```sh
sha256sum --check SHA256SUMS
```
