"""Write frozen.json from the current setup (ADR-0001). Then commit it and tag the commit:

uv run python -m scripts.freeze
git add frozen.json && git commit -m "chore: freeze prompts and config"
git tag prompts-frozen && git push origin prompts-frozen
"""

import json
import sys
from pathlib import Path

from backend.config import get_settings
from backend.data import resolve_data_source
from backend.experiment import ExperimentConfig
from backend.freeze import FROZEN_FILE, fingerprint


def main() -> int:
    settings = get_settings()
    source = resolve_data_source(Path(settings.data_dir))
    if source.kind != "mind" or settings.mock_llm or not settings.llm_model:
        print("Freeze only with real MIND, MOCK_LLM=false and a pinned LLM_MODEL.")
        return 2
    current = fingerprint(
        source,
        ExperimentConfig(),
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        options=settings.llm_options(),
    )
    Path(FROZEN_FILE).write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {FROZEN_FILE}. Commit it, then tag that commit 'prompts-frozen'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
