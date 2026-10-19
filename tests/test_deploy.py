"""scripts.deploy (#23, ADR-0011): the gcloud commands, checked as text. Nothing runs."""

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import pytest

from scripts import deploy

WHERE = ["--project", "my-proj", "--region", "europe-west2", "--repo", "twin"]
IMAGE = "europe-west2-docker.pkg.dev/my-proj/twin/twin-lab-demo"


def never(command: Sequence[str]) -> NoReturn:
    raise AssertionError(f"ran {command}")


def dry_run(action: str, capsys: pytest.CaptureFixture[str], *more: str) -> list[str]:
    assert deploy.main([action, *WHERE, *more, "--dry-run"], run=never, read=never) == 0
    return capsys.readouterr().out.splitlines()


def test_deploy_dry_run_prints_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert dry_run("deploy", capsys) == [
        "# refuse to deploy if the repo grants allUsers or allAuthenticatedUsers:",
        "gcloud artifacts repositories get-iam-policy twin --project=my-proj "
        "--location=europe-west2 --format=json",
        f"docker build --platform=linux/amd64 --target=demo -t {IMAGE}:demo .",
        "gcloud auth configure-docker europe-west2-docker.pkg.dev --quiet",
        f"docker push {IMAGE}:demo",
        f"gcloud run deploy twin-lab --image={IMAGE}:demo --project=my-proj "
        "--region=europe-west2 --allow-unauthenticated --min-instances=0 --max-instances=1 "
        "--memory=1Gi --port=8080 --set-env-vars=DEMO_MODE=1,MOCK_LLM=false "
        "--set-secrets=LLM_API_KEY=llm-api-key:latest",
    ]


def test_the_key_only_ever_comes_from_secret_manager(capsys: pytest.CaptureFixture[str]) -> None:
    out = "\n".join(dry_run("deploy", capsys, "--secret", "demo-key"))

    assert "--set-secrets=LLM_API_KEY=demo-key:latest" in out
    assert "LLM_API_KEY=" not in out.replace("--set-secrets=LLM_API_KEY=", "")
    assert "--env-file" not in out
    assert "--build-arg" not in out


def test_teardown_dry_run_deletes_the_service_and_the_image(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dry_run("teardown", capsys, "--service", "demo") == [
        "gcloud run services delete demo --project=my-proj --region=europe-west2 --quiet",
        f"gcloud artifacts docker images delete {IMAGE} --delete-tags --quiet",
    ]


@pytest.fixture
def in_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "demo-data").mkdir()
    return tmp_path


def test_deploy_runs_the_commands_in_order(in_repo: Path) -> None:
    ran: list[Sequence[str]] = []

    code = deploy.main(["deploy", *WHERE], run=ran.append, read=lambda _: '{"bindings": []}')

    assert code == 0
    assert [c[:2] for c in ran] == [
        ["docker", "build"],
        ["gcloud", "auth"],
        ["docker", "push"],
        ["gcloud", "run"],
    ]


@pytest.mark.parametrize("member", deploy.PUBLIC_MEMBERS)
def test_deploy_refuses_a_public_repo(in_repo: Path, member: str) -> None:
    policy = (
        f'{{"bindings": [{{"members": ["{member}"], "role": "roles/artifactregistry.reader"}}]}}'
    )

    assert deploy.main(["deploy", *WHERE], run=never, read=lambda _: policy) == 1


def test_deploy_needs_demo_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert deploy.main(["deploy", *WHERE], run=never, read=never) == 1


def test_a_failed_command_stops_the_rest(capsys: pytest.CaptureFixture[str]) -> None:
    ran: list[Sequence[str]] = []

    def fail(command: Sequence[str]) -> None:
        ran.append(command)
        raise subprocess.CalledProcessError(1, list(command))

    assert deploy.main(["teardown", *WHERE], run=fail, read=never) == 1
    assert len(ran) == 1
    assert "failed with exit code 1" in capsys.readouterr().out
