"""Command line: `demo` writes the fictional Northwind Optics exports to sample_data/ and builds the outputs; `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import report, simulate
from .checks import overall, pct, review, run_all, summary
from .model import load, parse_dt

OUTPUTS = ("report.html", "store-review.md", "stores.csv", "connectivity.csv", "devices-review.csv", "tickets-review.csv", "openings.csv",
           "visits.csv", "actions.csv", "findings.csv")


def run(data: Path, out: Path, title: str, as_of: datetime | None = None) -> dict:
    d = load(data, as_of)
    rv = review(d)
    findings = run_all(d, rv)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, rv, findings, title), encoding="utf-8")
    (out / "store-review.md").write_text(report.pack_md(d, rv, findings, title), encoding="utf-8")
    report.write_stores(d, rv, out / "stores.csv")
    report.write_connectivity(d, rv, out / "connectivity.csv")
    report.write_devices(d, rv, out / "devices-review.csv")
    report.write_tickets(d, rv, out / "tickets-review.csv")
    report.write_openings(d, rv, out / "openings.csv")
    report.write_visits(d, rv, out / "visits.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    sm = summary(d, rv)
    sm.update(overall=overall(findings), critical=sum(f.severity == "critical" for f in findings), warning=sum(f.severity == "warning" for f in findings))
    return sm


def _when(value: str) -> datetime:
    d = parse_dt(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="storehealth", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional exports to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, nargs="?", help="folder with stores.csv and the other exports")
    rv.add_argument("--data", dest="data_opt", type=Path, help="same as the positional folder")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Store IT health review")
    rv.add_argument("--as-of", type=_when, help="reference date (default: settings.json, or now)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, f"{simulate.ORG} · store IT health, week to 2 November 2026 (review of 3 November)")
    else:
        folder = a.data or a.data_opt
        if not folder:
            print("error: give the folder with the exports", file=sys.stderr)
            return 2
        try:
            sm = run(folder, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"{sm['overall'].upper()} · {sm['trading']} trading stores: {sm['red']} red, {sm['amber']} amber, {sm['green']} green · visits "
          f"{sm['visits']}, shipments {sm['ships']}, vendor calls {sm['vendors']} + {sm['vendor_estate']} estate-wide · primary lines "
          f"{pct(sm['uptime'], 2)}, {sm['failovers']} failovers · backup never tested {sm['never_tested']} · unsupported Windows {sm['unsupported']} · "
          f"openings {sm['openings']} · {sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
