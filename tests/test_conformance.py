"""The conformance kit: its examples reproduce, agree with the referee, and catch a fault."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest
from conftest import ROOT

from ym2612_python.chip import MCLK_PER_CYCLE
from ym2612_python.conformance import (
    diff_traces,
    load_manifest,
    main,
    manifest_from_dict,
    trace_manifest,
)

EXAMPLES = ROOT / "examples" / "conformance"
MANIFESTS = sorted(EXAMPLES.glob("*.json"))
REFEREES = ROOT / "reference" / "build-referees"


def test_there_are_examples() -> None:
    assert len(MANIFESTS) >= 9


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda path: path.stem)
def test_each_example_reproduces_its_committed_trace(path: Path) -> None:
    trace = path.with_suffix(".trace").read_text(encoding="utf-8").splitlines()
    assert diff_traces(trace_manifest(load_manifest(path)), trace) is None


def test_the_diff_reports_one_changed_value() -> None:
    """A gate that cannot fail proves nothing: one DAC value off by one is caught,
    and so is a missing last line."""
    path = EXAMPLES / "random-walk-ym2612.json"
    trace = path.with_suffix(".trace").read_text(encoding="utf-8").splitlines()
    index = next(i for i, line in enumerate(trace) if line.startswith("C ") and i > 1000)
    kind, slot, mol, *rest = trace[index].split()
    wrong = [*trace[:index], " ".join([kind, slot, str(int(mol) + 1), *rest]), *trace[index + 1 :]]
    difference = diff_traces(trace_manifest(load_manifest(path)), wrong)
    assert difference is not None and difference.line == index + 1
    assert diff_traces(trace_manifest(load_manifest(path)), trace[:-1]) is not None


def test_the_cli_traces_and_diffs() -> None:
    path = EXAMPLES / "dac-ym2612.json"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dac.trace"
        assert main(["trace", str(path), "--out", str(out)], stdout=io.StringIO()) == 0
        report = io.StringIO()
        assert main(["diff", str(path), str(out)], stdout=report) == 0
        assert "identical" in report.getvalue()
        out.write_text(out.read_text().replace("C 0", "C 1", 1))
        report = io.StringIO()
        assert main(["diff", str(path), str(out)], stdout=report) == 1
        assert "differ at line" in report.getvalue()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": 2}, "version"),
        ({"variant": "ym2203"}, "variant"),
        ({"surprise": 1}, "unknown manifest keys"),
        ({"events": [{"t": 5, "kind": "poke"}]}, "kind"),
        ({"events": [{"t": 9, "kind": "read"}, {"t": 5, "kind": "read"}]}, "tick order"),
        ({"events": [{"t": 99, "kind": "read"}], "ticks": 10}, "after the end"),
    ],
)
def test_bad_manifests_are_refused(change: dict, message: str) -> None:
    document = {"version": 1, "name": "x", "variant": "ym2612", "ticks": 100, "events": []}
    document.update(change)
    with pytest.raises(ValueError, match=message):
        manifest_from_dict(document)


# -- the examples against Nuked-OPN2 ---------------------------------------------------


def _comparable(path: Path) -> bool:
    """The referee drives no /IC, has no die-figures timer delay and always runs the
    generator, so the examples that exercise those are this chip's own."""
    document = json.loads(path.read_text())
    return (
        document.get("enabled", True)
        and not document.get("control_delay", 0)
        and all(event["kind"] != "ic" for event in document["events"])
    )


@pytest.mark.referee
@pytest.mark.skipif(
    not (REFEREES / "opn2_ref").exists(), reason="run `sh validation/build_referees.sh`"
)
@pytest.mark.parametrize("path", [p for p in MANIFESTS if _comparable(p)], ids=lambda p: p.stem)
def test_each_example_trace_agrees_with_nuked_opn2(path: Path, tmp_path: Path) -> None:
    import referees

    document = json.loads(path.read_text())
    writes = [event for event in document["events"] if event["kind"] == "write"]
    # A write at tick t is taken by the cycle under way at t (run() completes only the
    # cycles that end by t), which is the referee's cycle t // 42.
    events = [(e["t"] // MCLK_PER_CYCLE, e["port"], e["data"]) for e in writes]
    lines = [
        line.split()
        for line in path.with_suffix(".trace").read_text().splitlines()
        if line.startswith("C ")
    ]
    variant = document["variant"]
    ref_l, ref_r, ref_s = referees.run_opn2(events, len(lines), tmp_path, variant=variant)
    for cycle, (_kind, _slot, mol, mor, status, _irq) in enumerate(lines):
        assert (int(mol), int(mor), int(status)) == (ref_l[cycle], ref_r[cycle], ref_s[cycle]), (
            f"{path.stem}: cycle {cycle}"
        )
