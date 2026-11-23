"""check-refs over a seed whose `unique` field holds a list.

The seed schema only requires records to be objects, so `validate --stage
instantiate` passes such a seed. The `unique` invariant once put those values
in a set, the TypeError escaped to cli.py's catch-all, and the run's whole
check-refs output became one `[internal]` line naming no seed -- every real
finding hidden, and the orchestrator's one repair attempt pointed nowhere.
"""

from __future__ import annotations

from rubrica import cli
from rubrica.artifacts import read_json, write_json
from tests.toy import build_toy_run


def test_duplicate_list_ids_are_findings_against_the_seed(tmp_path, capsys):
    run = build_toy_run(tmp_path / "runs", upto="instantiate")
    seed_path = sorted(run.root.glob("04-instances/*/seed.json"))[0]
    sid = seed_path.parent.name
    seed = read_json(seed_path)
    tickets = seed["collections"]["tickets"]
    tickets.append(dict(tickets[0]))
    tickets[0]["ticket_id"] = ["T-1"]
    tickets[1]["ticket_id"] = ["T-1"]
    write_json(seed_path, seed)

    code = cli.main(["check-refs", "--run", str(run.root)])
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert code == 1
    assert not any("[internal]" in line for line in lines), out
    seed_lines = [line for line in lines if f"04-instances/{sid}/seed.json" in line]
    # The invariant's own duplicate finding, and the type finding the run
    # gave before the crash, both still print.
    assert any("inv-ticket-id-unique" in line and "duplicate" in line for line in seed_lines), out
    assert any(
        "field 'ticket_id' is declared integer but holds ['T-1']" in line for line in seed_lines
    ), out
