# Hosted demo on Cloud Run

A temporary, public, read-only copy of the app for the panel ([ADR-0011](adr/0011-docker-and-cloud-run-demo.md)). It runs with `DEMO_MODE=1`: replay, Hook, Seed, Population and Report work; new runs and population building are refused (403); the interview is the only LLM caller, rate-limited, with the recorded exchanges as its fallback.

The examples use `PROJECT=my-project`, `REGION=europe-west2`, `REPO=twin-lab`. Add `--dry-run` to `just deploy` or `just teardown` to print the commands without running them.

## One-time setup

```bash
gcloud config set project my-project

# APIs
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

# A private Docker repository. Private is the default: grant no allUsers / allAuthenticatedUsers.
# `just deploy` checks the repo's IAM policy and refuses a public one.
gcloud artifacts repositories create twin-lab --repository-format=docker --location=europe-west2

# The Gemini key: Secret Manager injects it at run time; it is never in the image
printf '%s' "$LLM_API_KEY" | gcloud secrets create llm-api-key --data-file=-

# A dedicated runtime identity for the public service, not the default compute account (which
# often holds project Editor). Its only grant is reading this one secret: no project-level roles.
gcloud iam service-accounts create twin-lab-run --display-name="Twin Lab demo (Cloud Run)"
gcloud secrets add-iam-policy-binding llm-api-key \
  --member="serviceAccount:twin-lab-run@my-project.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor
```

`just deploy` runs the service as `twin-lab-run@PROJECT.iam.gserviceaccount.com`. Deploying with `--service-account` needs `roles/iam.serviceAccountUser` on that account for whoever deploys; a project Owner already has it. The repo check covers repo-level IAM only: make sure no project-level binding grants `allUsers` Artifact Registry read either.

Docker must be running locally; `just deploy` runs `gcloud auth configure-docker` for the registry.

## Before each deploy

```bash
just demo-data             # demo-data/ from DATA_DIR: newest result run (or --run <id>), the hook's run, their news
just demo-serve            # rehearse on http://localhost:8080 with DEMO_MODE=1 (key from .env at run time)
```

`demo-data/` holds only the frozen result run, the Step 0 Hook's dev run (`config/hook.json`), the recorded interview's run (`config/interview_recorded.json`, if present), and the news items those runs mention. No `cache.sqlite` (the interview never uses the cache), no `.env`, no keys. It is gitignored and only ever enters the private demo image. With MIND-small and N=300 it is about 17 MB.

## Deploy

```bash
just deploy my-project europe-west2 twin-lab --dry-run   # print the commands
just deploy my-project europe-west2 twin-lab             # run them
```

This builds the `demo` image target (the runtime image plus `demo-data/`, owned by root so the app cannot write it), pushes it to `europe-west2-docker.pkg.dev/my-project/twin-lab/twin-lab-demo:demo` and deploys service `twin-lab` with:

- `--service-account=twin-lab-run@PROJECT.iam.gserviceaccount.com`: can read the key's secret and nothing else
- `--allow-unauthenticated`: a public URL, no sign-in
- `--min-instances=0 --max-instances=1`: one instance at most, because the interview's rate limits are counted in memory (ADR-0011 amendment)
- `--set-env-vars=DEMO_MODE=1,MOCK_LLM=false,LLM_MODEL=<the result run's model>` (the image also sets `DEMO_MODE=1`)
- `--set-secrets=LLM_API_KEY=llm-api-key:latest`
- `--memory=1Gi`: about 200 MiB resident after serving the test run's replay, measured on the real demo data

Options: `--model`, `--service`, `--secret`, `--tag`, `--memory` (see `uv run python -m scripts.deploy --help`).

## Teardown

```bash
just teardown my-project europe-west2 twin-lab --dry-run
just teardown my-project europe-west2 twin-lab
```

Deletes the Cloud Run service and the demo image (every tag). The repository and the secret stay; delete them by hand when the demo is over:

```bash
gcloud artifacts repositories delete twin-lab --location=europe-west2
gcloud secrets delete llm-api-key
```
