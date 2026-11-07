"""Every example's documented result and step count (the `# result:` /
`# steps:` and `// result:` / `// steps:` header lines) matches a headless run.

Run: python3 -m pytest tests/test_example_steps.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import example_steps  # noqa: E402


def test_example_headers_match_headless_runs(capsys):
    rc = example_steps.main()
    out = capsys.readouterr().out
    assert rc == 0, out[out.rfind("\n[") - 2000:] if "[" in out else out
