# Cloud Student Setup

The `cloud_student` profile is for advanced experiments with student credits.
The core Django app should generate portable manifests and Parquet/Arrow
artifacts. Provider execution stays outside the core.

## Cost Strategy

- Partition jobs by date, symbol, source, or feature family.
- Use spot or preemptible instances when the provider supports them.
- Save checkpoints and result manifests after every partition.
- Stop notebooks, VMs, and rented GPUs when jobs finish.
- Do not train without a job manifest and budget guard.
- Prefer smoke tests before full backfills.

## Generic Workflow

```powershell
python manage.py inspect_compute --profile cloud_student
```

Future planning commands should write JSON job specs with:

- inputs and outputs in Parquet/Arrow;
- partition metadata;
- max runtime;
- retry policy;
- budget guard;
- expected artifacts.

## Kaggle and Colab

Upload the project, requirements, input Parquet files, and generated job spec.
Install only the optional packages required by the selected experiment. Run one
partition first and download the result manifest and artifacts.

## GCP

Use a notebook, VM, or batch service with the smallest GPU/CPU that fits the
partition. Prefer preemptible resources for retryable jobs. Store inputs and
outputs in portable files; do not make the code depend on a GCP SDK.

## AWS

Use a notebook, EC2 instance, or batch runner. Prefer spot instances for
restartable jobs. Keep credentials outside the repository and keep job specs
provider-neutral.

## Azure

Use a notebook, VM, or batch runner. Prefer low-cost or interruptible capacity
when possible. Keep storage paths and commands in the manifest instead of in
Azure-specific code.

## No Vendor Lock-In

Provider templates may generate instructions, but the project should not
require AWS, GCP, Azure, Kaggle, Colab, RunPod, Modal, or any other SDK for the
core Django install.

