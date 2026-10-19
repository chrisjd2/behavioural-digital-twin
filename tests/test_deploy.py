"""scripts.deploy (#23, ADR-0011): the gcloud commands, checked as text. Nothing runs."""

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

from backend.runs import RUNS_SUBDIR, save_run
from scripts import deploy
from tests.test_build_demo_data import Lab

WHERE = ["--project", "my-proj", "--region", "europe-west2", "--repo", "twin"]
MODEL = ["--model", "gemini-3.7-flash"]
IMAGE = "europe-west2-docker.pkg.dev/my-proj/twin/twin-lab-demo"


def never(command: Sequence[str]) -> NoReturn:
    raise AssertionError(f"ran {command}")


def dry_run(action: str, capsys: pytest.CaptureFixture[str], *more: str) -> list[str]:
    assert deploy.main([action, *WHERE, *more, "--dry-run"], run=never, read=never) == 0
    return capsys.readouterr().out.splitlines()


def test_deploy_dry_run_prints_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert dry_run("deploy", capsys, *MODEL) == [
        "# refuse to deploy if the repo grants allUsers or allAuthenticatedUsers:",
        "gcloud artifacts repositories get-iam-policy twin --project=my-proj "
        "--location=europe-west2 --format=json",
        f"docker build --platform=linux/amd64 --target=demo -t {IMAGE}:demo .",
        "gcloud auth configure-docker europe-west2-docker.pkg.dev --quiet",
        f"docker push {IMAGE}:demo",
        f"gcloud run deploy twin-lab --image={IMAGE}:demo --project=my-proj "
        "--region=europe-west2 --service-account=twin-lab-run@my-proj.iam.gserviceaccount.com "
        "--allow-unauthenticated --min-instances=0 --max-instances=1 --memory=1Gi --port=8080 "
        "--set-env-vars=DEMO_MODE=1,MOCK_LLM=false,LLM_MODEL=gemini-3.7-flash "
        "--set-secrets=LLM_API_KEY=llm-api-key:latest",
    ]


def test_the_key_only_ever_comes_from_secret_manager(capsys: pytest.CaptureFixture[str]) -> None:
    out = "\n".join(dry_run("deploy", capsys, *MODEL, "--secret", "demo-key"))

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

    code = deploy.main(
        ["deploy", *WHERE, *MODEL], run=ran.append, read=lambda _: '{"bindings": []}'
    )

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

    assert deploy.main(["deploy", *WHERE, *MODEL], run=never, read=lambda _: policy) == 1


def test_only_members_make_a_repo_public(in_repo: Path) -> None:
    policy = '{"bindings": [{"members": ["user:a@b.c"], "condition": {"title": "no allUsers"}}]}'

    assert deploy.public_members(policy) == []
    assert deploy.main(["deploy", *WHERE, *MODEL], run=lambda _: None, read=lambda _: policy) == 0


def test_deploy_needs_demo_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert deploy.main(["deploy", *WHERE, *MODEL], run=never, read=never) == 1


def test_llm_model_defaults_to_the_result_run_in_demo_data(
    in_repo: Path, capsys: pytest.CaptureFixture[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    lab = Lab(tmp_path_factory.mktemp("deploy-lab"))
    save_run(replace(lab.result, model="gemini-frozen-001"), in_repo / "demo-data" / RUNS_SUBDIR)
    save_run(replace(lab.dev, model="gemini-dev-002"), in_repo / "demo-data" / RUNS_SUBDIR)

    out = "\n".join(dry_run("deploy", capsys))

    assert "LLM_MODEL=gemini-frozen-001" in out


def test_deploy_without_a_model_or_result_run_refuses(in_repo: Path) -> None:
    assert deploy.main(["deploy", *WHERE, "--dry-run"], run=never, read=never) == 1


def failing(ran: list[Sequence[str]]) -> Callable[[Sequence[str]], None]:
    def fail(command: Sequence[str]) -> None:
        ran.append(command)
        raise subprocess.CalledProcessError(1, list(command))

    return fail


def test_teardown_deletes_the_image_even_if_the_service_is_gone() -> None:
    ran: list[Sequence[str]] = []

    assert deploy.main(["teardown", *WHERE], run=failing(ran), read=never) == 1
    assert [c[:2] for c in ran] == [["gcloud", "run"], ["gcloud", "artifacts"]]


def test_a_failed_deploy_step_stops_the_rest(in_repo: Path) -> None:
    ran: list[Sequence[str]] = []

    code = deploy.main(
        ["deploy", *WHERE, *MODEL], run=failing(ran), read=lambda _: '{"bindings": []}'
    )

    assert code == 1
    assert len(ran) == 1
