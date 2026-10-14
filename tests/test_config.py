from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from newsring.config import Config, CountRange, Profile, SourceSpec, load_config
from tests.conftest import ROOT


def test_shipped_config_loads() -> None:
    config = load_config(ROOT / "newsring.toml")
    assert config.llm.model
    assert len(config.enabled_sources) >= 20
    assert config.base_dir == ROOT


def test_count_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="greater than"):
        CountRange(min=8, max=3)


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"interests": "x", "intrests": "typo"})


def test_duplicate_source_names_are_rejected() -> None:
    spec = SourceSpec(name="Same", url="https://example.com/feed")
    with pytest.raises(ValidationError, match="unique"):
        Config(profile=Profile(interests="x"), sources=[spec, spec])


def test_relative_paths_resolve_against_config_dir(tmp_path: Path) -> None:
    file = tmp_path / "c.toml"
    file.write_text(
        '[profile]\ninterests = "x"\n[[sources]]\nname = "a"\nurl = "https://a.example"\n',
        encoding="utf-8",
    )
    config = load_config(file)
    assert config.resolve(config.delivery.archive_dir) == (tmp_path / "news").resolve()
