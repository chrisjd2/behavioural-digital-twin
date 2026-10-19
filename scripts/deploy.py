"""Deploy the hosted demo to Cloud Run, or tear it down (ADR-0011). One-time setup: docs/deploy.md.

deploy: refuse a public Artifact Registry repo, build the demo image (the runtime image plus
demo-data/, `scripts.build_demo_data`), push it, and deploy a public, unauthenticated service
with DEMO_MODE on, at most one instance (the interview's limits are counted in memory) and the
LLM key from Secret Manager, never from the image. teardown: delete the service and the image.

    uv run python -m scripts.deploy deploy   --project P --region R --repo REPO [--dry-run]
    uv run python -m scripts.deploy teardown --project P --region R --repo REPO [--dry-run]
"""

import argparse
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

IMAGE_NAME = "twin-lab-demo"
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
            "--allow-unauthenticated",
            "--min-instances=0",
            "--max-instances=1",
            f"--memory={t.memory}",
            "--port=8080",
            "--set-env-vars=DEMO_MODE=1,MOCK_LLM=false",
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
    policy = read(repo_policy_command(t))
    if public := [m for m in PUBLIC_MEMBERS if m in policy]:
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
    parser.add_argument("--service", default=Target.service)
    parser.add_argument("--secret", default=Target.secret, help="Secret Manager secret name")
    parser.add_argument("--tag", default=Target.tag)
    parser.add_argument("--memory", default=MEMORY)
    parser.add_argument("--dry-run", action="store_true", help="Print the commands only")
    args = parser.parse_args(argv)
    target = Target(
        args.project, args.region, args.repo, args.service, args.secret, args.tag, args.memory
    )

    commands = (deploy_commands if args.action == "deploy" else teardown_commands)(target)
    if args.dry_run:
        if args.action == "deploy":
            print(f"# refuse to deploy if the repo grants {' or '.join(PUBLIC_MEMBERS)}:")
            print(shlex.join(repo_policy_command(target)))
        print("\n".join(shlex.join(c) for c in commands))
        return 0
    try:
        if args.action == "deploy" and (problem := deploy_problem(target, read)):
            print(problem)
            return 1
        for command in commands:
            print(shlex.join(command))
            run(command)
    except subprocess.CalledProcessError as exc:
        print(f"{shlex.join(exc.cmd)} failed with exit code {exc.returncode}; stopping.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
