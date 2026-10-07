from __future__ import annotations

from pathlib import Path

import pytest

from magi.personas import Persona, PersonaError, load_personas, resolve_persona_ref


def test_default_council(council: list[Persona]) -> None:
    assert [p.name for p in council] == ["MELCHIOR-1", "BALTHASAR-2", "CASPAR-3"]
    assert [p.title for p in council] == ["The Scientist", "The Guardian", "The Individual"]
    assert all(p.system_prompt.strip() and p.priorities for p in council)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("BALTHASAR-2", "balthasar"),
        ("balthasar", "balthasar"),
        ("Balthasar-2 (The Guardian)", "balthasar"),
        ("The Guardian", "balthasar"),
        ("caspar3", "caspar"),
        ("GENDO", None),
        ("", None),
    ],
)
def test_resolve_persona_ref(council: list[Persona], ref: str, expected: str | None) -> None:
    match = resolve_persona_ref(ref, council)
    assert (match.id if match else None) == expected


def write(directory: Path, name: str, **fields: object) -> None:
    body = {"name": name.upper(), "title": "T", "color": "#fff", "system_prompt": "x", **fields}
    lines = [
        f"{key}: {value!r}" if isinstance(value, str) else f"{key}: {value}"
        for key, value in body.items()
    ]
    (directory / f"{name}.yaml").write_text("\n".join(lines) + "\n")


def test_custom_council_is_sorted_by_order(tmp_path: Path) -> None:
    write(tmp_path, "zed", id="zed", order=1)
    write(tmp_path, "amy", id="amy", order=2)
    assert [p.id for p in load_personas(tmp_path)] == ["zed", "amy"]


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    write(tmp_path, "one", id="same")
    write(tmp_path, "two", id="same")
    with pytest.raises(PersonaError, match="duplicate"):
        load_personas(tmp_path)


def test_council_needs_two_members(tmp_path: Path) -> None:
    write(tmp_path, "solo", id="solo")
    with pytest.raises(PersonaError, match="at least two"):
        load_personas(tmp_path)


def test_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(PersonaError, match="no persona files"):
        load_personas(tmp_path)


def test_relative_paths_in_settings_resolve_against_repo() -> None:
    from magi.paths import REPO_ROOT
    from magi.settings import Settings

    settings = Settings(_env_file=None, traces_dir=Path("my-traces"), personas_dir=Path("/abs/p"))
    assert settings.traces_dir == REPO_ROOT / "my-traces"
    assert settings.personas_dir == Path("/abs/p")
