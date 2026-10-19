"""Deploy the hosted demo to Cloud Run, or tear it down (ADR-0011). One-time setup: docs/deploy.md.

deploy: refuse a public Artifact Registry repo, build the demo image (the runtime image plus
demo-data/, `scripts.build_demo_data`), push it, and deploy a public, unauthenticated service
with DEMO_MODE on, at most one instance (the interview's limits are counted in memory), its
own service account (which can read only the key's secret) and the LLM key from Secret
Manager, never from the image. teardown: delete the service and the image.

    uv run python -m scripts.deploy deploy   --project P --region R --repo REPO [--dry-run]
    uv run python -m scripts.deploy teardown --project P --region R --repo REPO [--dry-run]
"""

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.run_views import list_runs
from backend.runs import RUNS_SUBDIR

IMAGE_NAME = "twin-lab-demo"
SERVICE_ACCOUNT = "twin-lab-run"  # created in docs/deploy.md's one-time setup
DEMO_DATA = Path("demo-data")
PUBLIC_MEMBERS = ("allUsers", "allAuthenticatedUsers")
# Measured on the real demo-data (16.8 MB): ~200 MiB resident after serving the test run's
# replay (3.7 MB of events). 1Gi leaves room for concurrent replays and the interview.
MEMORY = "1Gi"

Command = list[str]


@dataclass(frozen=True)
class Target:
    project: str
    region: str
    repo: str
    model: str = ""  # LLM_MODEL, so /api/status names the frozen run's model
    service: str = "twin-lab"
    secret: str = "llm-api-key"
    tag: str = "demo"
    memory: str = MEMORY

    @property
    def registry(self) -> str:
        return f"{self.region}-docker.pkg.dev"

    @property
    def image(self) -> str:
        return f"{self.registry}/{self.project}/{self.repo}/{IMAGE_NAME}"

    @property
    def service_account(self) -> str:
        return f"{SERVICE_ACCOUNT}@{self.project}.iam.gserviceaccount.com"


def repo_policy_command(t: Target) -> Command:
    return [
        "gcloud", "artifacts", "repositories", "get-iam-policy", t.repo,
        f"--project={t.project}", f"--location={t.region}", "--format=json",
    ]  # fmt: skip


def deploy_commands(t: Target) -> list[Command]:
    tagged = f"{t.image}:{t.tag}"
    return [
        ["docker", "build", "--platform=linux/amd64", "--target=demo", "-t", tagged, "."],
        ["gcloud", "auth", "configure-docker", t.registry, "--quiet"],
        ["docker", "push", tagged],
        [
            "gcloud", "run", "deploy", t.service,
            f"--image={tagged}",
            f"--project={t.project}",
            f"--region={t.region}",
            f"--service-account={t.service_account}",
            "--allow-unauthenticated",
            "--min-instances=0",
            "--max-instances=1",
            f"--memory={t.memory}",
            "--port=8080",
            f"--set-env-vars=DEMO_MODE=1,MOCK_LLM=false,LLM_MODEL={t.model}",
            f"--set-secrets=LLM_API_KEY={t.secret}:latest",
        ],
    ]  # fmt: skip


def teardown_commands(t: Target) -> list[Command]:
    return [
        [
            "gcloud", "run", "services", "delete", t.service,
            f"--project={t.project}", f"--region={t.region}", "--quiet",
        ],
        ["gcloud", "artifacts", "docker", "images", "delete", t.image, "--delete-tags", "--quiet"],
    ]  # fmt: skip


def result_model(demo_data: Path) -> str | None:
    """The model of the result run in demo-data/, the run the demo reports."""
    runs = list_runs(demo_data / RUNS_SUBDIR).runs if demo_data.is_dir() else []
    return next((r.model for r in runs if r.is_result), None)


def public_members(policy_json: str) -> list[str]:
    policy = json.loads(policy_json or "{}")
    members = {m for b in policy.get("bindings", []) for m in b.get("members", [])}
    return [m for m in PUBLIC_MEMBERS if m in members]


def executable(command: Sequence[str]) -> list[str]:
    """`gcloud` is `gcloud.cmd` on Windows, which CreateProcess does not find by itself."""
    return [shutil.which(command[0]) or command[0], *command[1:]]


def run_command(command: Sequence[str]) -> None:
    subprocess.run(executable(command), check=True)


def read_command(command: Sequence[str]) -> str:
    return subprocess.run(executable(command), check=True, capture_output=True, text=True).stdout


def deploy_problem(t: Target, read: Callable[[Sequence[str]], str]) -> str | None:
    if not DEMO_DATA.is_dir():
        return "No demo-data/: run `just demo-data` first."
    if public := public_members(read(repo_policy_command(t))):
        return f"Artifact Registry repo {t.repo} grants {public[0]}: it must be private."
    return None


def main(
    argv: list[str] | None = None,
    run: Callable[[Sequence[str]], None] = run_command,
    read: Callable[[Sequence[str]], str] = read_command,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["deploy", "teardown"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--repo", required=True, help="A private Artifact Registry repo")
    parser.add_argument("--model", default=None, help="Defaults to the result run's model")
    parser.add_argument("--service", default=Target.service)
    parser.add_argument("--secret", default=Target.secret, help="Secret Manager secret name")
    parser.add_argument("--tag", default=Target.tag)
    parser.add_argument("--memory", default=MEMORY)
    parser.add_argument("--dry-run", action="store_true", help="Print the commands only")
    args = parser.parse_args(argv)
    deploying = args.action == "deploy"
    model = args.model or (result_model(DEMO_DATA) if deploying else "")
    if model is None:
        print("No result run in demo-data/ to take LLM_MODEL from: pass --model.")
        return 1
    target = Target(
        args.project, args.region, args.repo, model,
        args.service, args.secret, args.tag, args.memory,
    )  # fmt: skip

    commands = deploy_commands(target) if deploying else teardown_commands(target)
    if args.dry_run:
        if deploying:
            print(f"# refuse to deploy if the repo grants {' or '.join(PUBLIC_MEMBERS)}:")
            print(shlex.join(repo_policy_command(target)))
        print("\n".join(shlex.join(c) for c in commands))
        return 0
    try:
        problem = deploy_problem(target, read) if deploying else None
    except subprocess.CalledProcessError as exc:
        problem = f"Could not read the repo's IAM policy (exit code {exc.returncode})."
    if problem:
        print(problem)
        return 1
    failed = 0
    for command in commands:
        print(shlex.join(command))
        try:
            run(command)
        except subprocess.CalledProcessError as exc:
            print(f"Failed with exit code {exc.returncode}.")
            failed += 1
            if deploying:  # each deploy step needs the one before
                return 1
    # Teardown tries every step: an already-deleted service must not keep the image alive.
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
