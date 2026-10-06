#!/usr/bin/env python3
"""
Regression test: pytoy's behaviour on the example assembly programs must match
the committed snapshot table (tests/snapshot/asm_snapshot.json).

This rebuilds the table in-process (fast, stdlib + pytoy only) via
scripts/gen_snapshot.py and asserts it equals the checked-in JSON. If pytoy's
assembler or CPU core ever drifts, this fails — and it's the same table a Kotlin
port (ktoy) is verified against, so both stay in lock-step.

Regenerate the snapshot file after an intended change:
    python3 scripts/gen_snapshot.py
"""

import os
import sys
import json

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import gen_snapshot  # noqa: E402

SNAPSHOT_PATH = os.path.join(REPO_ROOT, "tests", "snapshot", "asm_snapshot.json")


def load_committed():
    with open(SNAPSHOT_PATH) as f:
        return json.load(f)


def test_snapshot_matches_committed():
    """The freshly generated table must equal the committed snapshot JSON."""
    expected = load_committed()
    actual = gen_snapshot.build_snapshot()
    assert actual == expected, (
        "pytoy behaviour drifted from tests/snapshot/asm_snapshot.json. "
        "If this change is intended, regenerate with "
        "`python3 scripts/gen_snapshot.py` and commit the new file."
    )


def test_snapshot_roundtrips_json():
    """The committed file must be exactly what the generator would write
    (deterministic sorted keys + indent=2), so it always diffs cleanly."""
    committed_text = open(SNAPSHOT_PATH).read()
    table = gen_snapshot.build_snapshot()
    generated_text = json.dumps(table, sort_keys=True, indent=2) + "\n"
    assert generated_text == committed_text, (
        "asm_snapshot.json is not in canonical form; regenerate with "
        "`python3 scripts/gen_snapshot.py`."
    )


@pytest.mark.parametrize("name", sorted(load_committed().keys()))
def test_every_example_assembles(name):
    """Every example must assemble cleanly and not hit the step cap."""
    entry = load_committed()[name]
    assert entry.get("assembled") is True, f"{name} failed to assemble"
    assert entry.get("hit_cap") is False, f"{name} hit the step cap"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
