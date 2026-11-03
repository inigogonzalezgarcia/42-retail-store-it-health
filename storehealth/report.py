"""Outputs: report.html (verdict, tiles, the store grid by region, one section per area, the visit and ship list, findings),
store-review.md (the weekly pack for the retail operations meeting), and the CSVs: stores, connectivity, devices, tickets, openings,
visits, actions and findings."""
from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from .checks import AREAS, CRITICAL, INFO, ORDER, VERDICT, WARNING, Finding, all_issues, area_status, now_label, overall, pct, summary
from .model import FILES, Data

e = html.escape
KIND_LABEL = {"visit": "Visit", "ship": "Ship", "vendor": "Vendor call", "remote": "Remote"}


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _t(v) -> str:
    if not v:
        return ""
    return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else v.strftime("%Y-%m-%d")


def _f(x, k=3) -> str:
    return "" if x is None else f"{x:.{k}f}"


def _iss(issues) -> str:
    return " | ".join(f"{i.code} {i.text}" for i in issues)


def _codes(issues) -> str:
    return "; ".join(dict.fromkeys(i.code for i in issues if i.severity != INFO))


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO])


def store_rows(rv: dict) -> list[dict]:
    return sorted(rv["stores"].values(), key=lambda r: (r["store"].region, r["store"].id))


def write_stores(d: Data, rv: dict, path: Path) -> None:
    rows = []
    for r in store_rows(rv):
        st, c, t = r["store"], rv["conn"][r["store"].id], rv["tickets"][r["store"].id]
        kinds = Counter(i.kind for i in r["issues"] if i.severity != INFO)
        rows.append([st.id, st.name, st.region, st.city, st.country, st.format, st.status, st.field_tech, r["rag"], r["prev"],
                     sum(i.severity == CRITICAL for i in r["issues"]), sum(i.severity == WARNING for i in r["issues"]), _f(c["uptime"], 4),
                     c["failovers"] if c["days"] else "", f"{c['backup_minutes']:.0f}" if c["days"] else "", _t(c["backup_test"]),
                     _f(c["data_share"]), _f(c["tunnel_up"], 4), c["flap_days"] if c["days"] else "", t["tickets"], _f(t["ratio"], 2), t["open"],
                     kinds.get("visit", 0), kinds.get("ship", 0), kinds.get("vendor", 0), _iss([i for i in r["issues"] if i.severity != INFO])])
    _w(path, ["store_id", "name", "region", "city", "country", "format", "status", "field_tech", "rag", "last_week_rag", "critical", "warnings",
              "primary_uptime_7d", "failovers_7d", "backup_minutes_7d", "backup_last_test", "backup_data_share", "tunnel_up_7d", "tunnel_drop_days_7d",
              "tickets_30d", "ticket_ratio_to_median", "open_tickets", "visit_items", "ship_items", "vendor_items", "issues"], rows)


def write_connectivity(d: Data, rv: dict, path: Path) -> None:
    rows = []
    for r in store_rows(rv):
        st, c = r["store"], rv["conn"][r["store"].id]
        if not c["days"]:
            continue
        p = c["prev"]
        hr = c["drop_hours"].most_common(1)
        iss = [i for i in r["issues"] if i.code.startswith("CON")]
        rows.append([st.id, st.name, st.region, st.format, st.status, st.backup or "none", _f(c["uptime"], 4), _f(p["uptime"], 4), c["failovers"],
                     p["failovers"], f"{c['backup_minutes']:.0f}", f"{p['backup_minutes']:.0f}", _t(c["backup_test"]),
                     "" if c["data_used"] is None else f"{c['data_used']:.0f}", "" if c["data_cap"] is None else f"{c['data_cap']:.0f}",
                     _f(c["data_share"]), _f(c["tunnel_up"], 4), c["tunnel_drops"], p["tunnel_drops"], c["flap_days"], hr[0][0] if hr else "",
                     c["anyconnect"], _codes(iss), _iss(iss)])
    _w(path, ["store_id", "name", "region", "format", "status", "backup_line", "primary_uptime_7d", "primary_uptime_prev_7d", "failovers_7d",
              "failovers_prev_7d", "backup_minutes_7d", "backup_minutes_prev_7d", "backup_last_test", "data_used_mb", "data_cap_mb", "data_share",
              "tunnel_up_7d", "tunnel_drops_7d", "tunnel_drops_prev_7d", "tunnel_drop_days_7d", "tunnel_peak_hour", "anyconnect_failures_7d", "codes",
              "issues"], rows)


def write_devices(d: Data, rv: dict, path: Path) -> None:
    rows = []
    for r in rv["devices"]:
        dev, st = r["dev"], r["store"]
        rows.append([dev.store, st.name if st else "", st.region if st else "", st.status if st else "unknown store", dev.name, dev.role, dev.source,
                     dev.model, dev.os, dev.os_version, _t(r["os_end"]), _t(dev.last_sync), _f(r["age_h"], 1), dev.health, _t(dev.battery_date), "", "",
                     _codes(r["issues"]), "; ".join(dict.fromkeys(i.action for i in r["issues"])), _iss(r["issues"])])
    for r in rv["printers"]:
        p, st = r["p"], r["store"]
        rows.append([p.store, st.name if st else "", st.region if st else "", st.status if st else "unknown store", p.name, f"{p.kind} printer",
                     "SNMP", p.model, "", "", "", _t(p.last_seen), _f(r["age_h"], 1), p.status + (f" ({p.error})" if p.error else ""), "",
                     _f(p.toner, 2), r["jams"], _codes(r["issues"]), "; ".join(dict.fromkeys(i.action for i in r["issues"])), _iss(r["issues"])])
    rows.sort(key=lambda x: (x[0], x[4]))
    _w(path, ["store_id", "store", "region", "store_status", "device", "role", "source", "model", "operatingSystem", "osVersion", "end_of_servicing",
              "last_seen", "hours_since_seen", "health_or_status", "battery_date", "toner", "jam_tickets_30d", "codes", "action", "issues"], rows)


def write_tickets(d: Data, rv: dict, path: Path) -> None:
    since = d.as_of.timestamp() - d.settings.ticket_days * 86400
    rows = []
    for r in rv["ticket_rows"]:
        t, st = r["t"], r["store"]
        if not t.is_open and (not t.opened or t.opened.timestamp() < since):
            continue
        rows.append([t.number, t.store, st.name if st else "", st.region if st else "", st.field_tech if st else "", t.category, t.priority, t.state,
                     _t(t.opened), _t(t.closed), "yes" if t.is_open else "no", _f(r["age_h"], 1), f"{r['sla']:g}", "yes" if r["past_sla"] else "no",
                     "yes" if r["paused"] else "no", "yes" if t.field_visit else "no", t.vendor, t.vendor_ref, t.short_description, t.ci,
                     _codes(r["issues"])])
    _w(path, ["number", "store_id", "store", "region", "field_tech", "category", "priority", "state", "opened", "closed", "open", "age_hours",
              "sla_hours", "past_sla", "sla_paused", "field_visit", "vendor", "vendor_ref", "short_description", "ci", "codes"], rows)


def write_openings(d: Data, rv: dict, path: Path) -> None:
    rows = []
    for o in rv["openings"]:
        st = o["store"]
        verdict = {CRITICAL: "action needed", WARNING: "attention"}.get(min((i.severity for i in o["issues"]), key=ORDER.get, default=INFO), "on track")
        items = o["items"] or [None]
        for c in items:
            rows.append([st.id, st.name, st.region, st.format, st.field_tech, o["event"], _t(o["date"]), "" if o["days"] is None else o["days"], verdict,
                         c.item if c else "", c.owner if c else "", _t(c.due) if c else "", c.status if c else "",
                         "yes" if c and not c.done and c.due and c.due < d.today else "no", c.notes if c else ""])
    _w(path, ["store_id", "name", "region", "format", "field_tech", "event", "date", "days_to_go", "verdict", "item", "owner", "due", "status",
              "overdue", "notes"], rows)


def write_visits(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["region", "field_tech", "rank", "store_id", "store", "format", "city", "rag", "kind", "severity", "what", "codes", "reasons"],
       [[v["store"].region, v["store"].field_tech, v["rank"], v["store"].id, v["store"].name, v["store"].format, v["store"].city, v["rag"], v["kind"],
         v["severity"], v["what"], _codes(v["issues"]), " | ".join(i.text for i in v["issues"])] for v in rv["visits"]])


# ---------------------------------------------------------------- the pack

TODO = "**[TO COMPLETE]**"


def _md(x) -> str:
    return str(x).replace("|", "/")


def short(i, st=None) -> str:
    """The issue text without the store's own label, which the table already shows."""
    if not st:
        return i.text
    lb = f"{st.id} {st.name}"
    t = i.text[len(lb) + 2:] if i.text.startswith(lb + ": ") else i.text
    return t.replace(f" at {lb}", "")


def _reasons(issues, k: int = 3, st=None) -> str:
    xs = [i for i in issues if i.severity != INFO]
    out = "; ".join(short(i, st) for i in xs[:k])
    return out + (f" (+{len(xs) - k} more)" if len(xs) > k else "")


def vendor_calls(rv: dict) -> list:
    """One line per store (all its vendor items together) and one per estate-wide issue: (severity, store, what, ask)."""
    out = [(i.severity, "estate", i.text, i.action) for i in rv["estate"] if i.kind == "vendor" and i.severity != INFO]
    for v in rv["visits"]:
        if v["kind"] == "vendor":
            st = v["store"]
            out.append((v["severity"], f"{st.id} {st.name}", "; ".join(short(i, st) for i in v["issues"]), v["what"]))
    return sorted(out, key=lambda x: (ORDER[x[0]], x[1] != "estate", x[1], x[2]))


def _delta(a, b, lower_better=True) -> str:
    if a is None or b is None:
        return "–"
    if abs(a - b) < 1e-9:
        return "same"
    worse = (a > b) == lower_better
    return ("worse" if worse else "better")


def trend_rows(tr: dict) -> list[tuple]:
    n, p = tr["now"], tr["prev"]
    return [("Primary line availability (estate average)", pct(n["uptime"], 2), pct(p["uptime"], 2), _delta(n["uptime"], p["uptime"], lower_better=False)),
            ("Failovers to the backup router", str(n["failovers"]), str(p["failovers"]), _delta(n["failovers"], p["failovers"])),
            ("Stores that failed over", str(n["stores_failover"]), str(p["stores_failover"]), _delta(n["stores_failover"], p["stores_failover"])),
            ("Minutes on backup", f"{n['backup_minutes']:,.0f}", f"{p['backup_minutes']:,.0f}", _delta(n["backup_minutes"], p["backup_minutes"])),
            ("Site-to-site tunnel drops", str(n["tunnel_drops"]), str(p["tunnel_drops"]), _delta(n["tunnel_drops"], p["tunnel_drops"])),
            ("Store tickets opened", str(n["tickets"]), str(p["tickets"]), _delta(n["tickets"], p["tickets"])),
            ("Tickets that needed a field visit", str(n["visits"]), str(p["visits"]), _delta(n["visits"], p["visits"]))]


def by_tech(rv: dict) -> list[tuple]:
    g = defaultdict(list)
    for v in rv["visits"]:
        g[(v["store"].region, v["store"].field_tech or "(no technician)")].append(v)
    return sorted(g.items())


def pack_md(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s, sm, st = d.settings, summary(d, rv), area_status(findings)
    tr = rv["trend"]
    out = [f"# {title}", "",
           f"> Generated by storehealth on {now_label(d.as_of)} from the exports listed under *Scope and evidence*. Read-only: nothing was changed "
           f"in Intune, Active Directory, the monitoring tool or the ITSM tool. Sections marked {TODO} are for the meeting.", "",
           f"**Overall: {overall(findings).upper()}**", "", "| Area | Status | To act on |", "|---|---|---|"]
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        out.append(f"| {a} | {'ON TRACK' if st[a] == 'ok' else VERDICT[st[a]].upper()} | {n} |")
    a, b = tr["window"]
    out += ["", "## Headlines", "",
            f"- {sm['trading']} trading stores: **{sm['red']} red**, {sm['amber']} amber, {sm['green']} green; {sm['openings']} openings in the next "
            f"{s.opening_weeks} weeks, {sm['refurb']} in refurbishment, {sm['closed_pending']} closed stores with devices not recovered.",
            f"- This week: {sm['visits']} store visits, {sm['ships']} shipments and {sm['vendors']} stores with a vendor call, plus "
            f"{sm['vendor_estate']} estate-wide vendor calls.",
            f"- Connectivity ({a:%d %b} to {b:%d %b}): primary lines {pct(sm['uptime'], 2)} available on average, {sm['failovers']} failovers at "
            f"{sm['on_backup']} stores; {sm['never_tested']} backup routers never tested, {sm['no_backup']} stores with no backup line.",
            f"- Devices: {sm['unsupported']} store or back-office computers on Windows out of support.",
            f"- Tickets: {sm['tickets']} in {s.ticket_days} days (median {sm['median']:g} per store), {sm['past_sla']} open past SLA, "
            f"{sm['vendor_open']} open with a vendor.",
            f"- Users: {sm['joiners']} joiners in the next {s.joiner_days} days without an account, {sm['leavers']} leavers still enabled.",
            "", "## Scope and evidence", "", f"- Organisation: {s.organisation}", f"- Reference date: {d.as_of:%a %d %b %Y %H:%M}",
            f"- Week reviewed: {a:%a %d %b} to {b:%a %d %b}; tickets: last {s.ticket_days} days", "", "| Source | File | Records |", "|---|---|---|"]
    out += [f"| {FILES.get(k, k)} | `{k}` | {v} |" for k, v in d.sources.items()]
    # 1 red stores
    red = [r for r in store_rows(rv) if r["rag"] == "red"]
    out += ["", "## 1. Red stores and why", "", "| Store | Region | Format | Technician | Last week | Why |", "|---|---|---|---|---|---|"]
    for r in sorted(red, key=lambda r: (r["store"].region, r["store"].id)):
        x = r["store"]
        out.append(f"| {x.id} {_md(x.name)}{'' if x.trading else f' ({x.status})'} | {x.region} | {x.format} | {x.field_tech} | {r['prev'] or '–'} | "
                   f"{_md(_reasons([i for i in r['issues'] if i.severity == CRITICAL], 3, x))} |")
    reg = defaultdict(Counter)
    for r in store_rows(rv):
        if r["store"].trading:
            reg[r["store"].region][r["rag"]] += 1
    out += ["", "| Region | Technician | Red | Amber | Green |", "|---|---|---|---|---|"]
    techs = {x.region: x.field_tech for x in d.stores}
    for g, c in sorted(reg.items()):
        out.append(f"| {g} | {techs.get(g, '')} | {c.get('red', 0)} | {c.get('amber', 0)} | {c.get('green', 0)} |")
    # 2 visits and shipments
    out += ["", "## 2. Visits and shipments by technician", "", "Ranked by severity within each technician; `visits.csv` has every line."]
    for (region, tech), vs in by_tech(rv):
        out += ["", f"### {region} · {tech}", "", "| # | Store | Status | Kind | What | Why |", "|---|---|---|---|---|---|"]
        for v in vs:
            if v["kind"] == "vendor":
                continue
            out.append(f"| {v['rank']} | {v['store'].id} {_md(v['store'].name)} | {v['rag'].upper()} | {KIND_LABEL[v['kind']]} | {_md(v['what'])} | "
                       f"{_md(_reasons(v['issues'], 2, v['store']))} |")
    # 3 vendor calls
    out += ["", "## 3. Vendor calls", "", "| Severity | Store | What | Ask |", "|---|---|---|---|"]
    for sev, sid, text, act in vendor_calls(rv):
        out.append(f"| {sev} | {_md(sid)} | {_md(text)} | {_md(act)} |")
    # 4 openings
    out += ["", "## 4. Openings, closings and refurbishments", "", f"Openings in the next {s.opening_weeks} weeks:", "",
            "| Store | Opens | Days | Done | Overdue or blocked | Status |", "|---|---|---|---|---|---|"]
    for o in rv["openings"]:
        if not o["event"].startswith("open") or o["days"] is None or not 0 <= o["days"] <= s.opening_weeks * 7:
            continue
        late = [c for c in o["items"] if not c.done and (c.blocked or (c.due and c.due < d.today))]
        sev = min((i.severity for i in o["issues"]), key=ORDER.get, default=INFO)
        out.append(f"| {o['store'].id} {_md(o['store'].name)} ({o['store'].format}) | {o['date']:%a %d %b} | {o['days']} | "
                   f"{sum(c.done for c in o['items'])} of {len(o['items'])} | {_md('; '.join(f'{c.item} ({c.status})' for c in late)) or '–'} | "
                   f"{({CRITICAL: 'ACTION NEEDED', WARNING: 'ATTENTION'}).get(sev, 'ON TRACK')} |")
    out.append("")
    for o in rv["openings"]:
        if o["event"].startswith("open"):
            continue
        out += [f"- **{o['event'].capitalize()}** {_md(i.text)}" for i in o["issues"]]
    # 5 connectivity
    out += ["", "## 5. Connectivity", "", "| Region | Trading stores | Tunnel flapping | Share | Peak hour of the drops |", "|---|---|---|---|---|"]
    for g, x in rv["regions"].items():
        hr = x["hours"].most_common(1)
        out.append(f"| {g} | {x['stores']} | {x['flapping']} | {pct(x['share'])} | {f'{hr[0][0]:02d}:00' if hr and x['flapping'] else '–'} |")
    out.append("")
    for code in ("CON-01", "CON-02", "CON-04", "CON-05", "CON-07", "CON-03", "CON-08"):
        for f in findings:
            if f.code == code and f.severity != INFO:
                out.append(f"- **{f.code}** {_md(f.subject)}: {_md(f.detail)}")
    # 6 devices, 7 tickets, 8 users
    for n, (name, pre) in enumerate((("Devices", "DEV"), ("Tickets", "TKT"), ("Users", "USR")), start=6):
        out += ["", f"## {n}. {name}", ""]
        xs = [f for f in findings if f.code.startswith(pre) and f.severity != INFO]
        out += [f"- **{f.code}** {_md(f.subject)} ({f.severity}): {_md(f.detail)}" for f in xs] or ["Nothing to report."]
        if pre == "TKT":
            top = sorted(((rv["tickets"][x.id]["tickets"], x) for x in d.stores if x.trading), key=lambda t: (-t[0], t[1].id))[:5]
            out += ["", f"Most tickets in {s.ticket_days} days (estate median {sm['median']:g}): "
                    + ", ".join(f"{x.id} {n_}" for n_, x in top) + "."]
    # 9 trend
    out += ["", "## 9. Trend against last week", "", "| Measure | This week | Last week | |", "|---|---|---|---|"]
    out += [f"| {a_} | {b_} | {c_} | {d_} |" for a_, b_, c_, d_ in trend_rows(tr)]
    if tr["has_prev"]:
        out += ["", f"Red stores (whole estate, including openings and closed stores): {tr['red_now']} this week, {tr['red_prev']} last week. "
                f"New red: {', '.join(tr['new_red']) or 'none'}. Back from red: {', '.join(tr['fixed']) or 'none'}."]
    out += ["", "## Findings", ""]
    for f in findings:
        if f.severity == INFO:
            continue
        out += [f"### {f.code} · {f.subject} ({f.severity})", "", _md(f.detail), "", f"Next step: {f.fix} Owner: {f.owner}.", ""]
    out += ["## Actions", "", "| Ref | Action | Next step | Owner | Due |", "|---|---|---|---|---|"]
    out += [f"| {f.code} | {_md(f.subject)} | {f.fix} | {f.owner} | {TODO if f.severity == CRITICAL else ''} |" for f in findings if f.severity != INFO]
    out += ["", "## Notes", "",
            "- A store is red when it has a critical issue (it may not sell or operate normally tomorrow, or it needs action today), amber with a "
            "warning, green otherwise. Stores in refurbishment are not checked until they reopen; closed stores only for devices and accounts.",
            f"- Connectivity uses the last {s.week_days} full days; the previous {s.week_days} days give the trend. Tickets use the last "
            f"{s.ticket_days} days; tickets on hold or awaiting a vendor do not count against the SLA.",
            "- Kind of action: visit (field technician), ship (courier to the store), vendor call (telco, printer vendor, payment provider) or "
            "remote (central IT).",
            f"- Decisions of the meeting: {TODO}", "",
            "## Sign-off", "", f"- Prepared by (central IT): {TODO}", f"- Reviewed with (retail operations): {TODO}", f"- Date: {TODO}", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;--g:#d6efe0;--a:#fbe7c4;--r:#f8d3cf;--n:#eceff3}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0;--g:#1d3b2b;--a:#4a3818;--r:#4d201c;--n:#262d35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}h3{font-size:15px;margin:18px 0 8px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical{color:var(--bad)}.warning{color:var(--warn)}.info{color:var(--info)}.ok{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.pill.on-track,.pill.green{color:var(--ok)}.pill.attention,.pill.amber{color:var(--warn)}.pill.action-needed,.pill.red{color:var(--bad)}
td.subj{min-width:190px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:380px}td.sm{font-size:13px}
.brk{overflow-wrap:anywhere;word-break:break-word}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.reg{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.reg h3{margin:0 0 2px}
.cells{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.cell{display:inline-block;width:52px;padding:3px 0;text-align:center;border-radius:5px;font-size:11px;font-variant-numeric:tabular-nums;border:1px solid var(--line)}
.cell.green{background:var(--g)}.cell.amber{background:var(--a)}.cell.red{background:var(--r);font-weight:700}.cell.grey{background:var(--n);color:var(--muted)}
.legend span{margin-right:14px;font-size:13px}.sw{display:inline-block;width:14px;height:10px;border-radius:2px;margin-right:4px;vertical-align:middle}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def _vpill(v: str) -> str:
    return _pill(v.replace(" ", "-"), v.upper())


def _issues(issues) -> str:
    xs = sorted(issues, key=lambda x: (ORDER[x.severity], x.code))
    return "<br>".join(f"<span class='{x.severity}'>●</span> <b>{e(x.code)}</b> {e(x.text)}" for x in xs) or "<span class='muted'>–</span>"


def _table(head: list[str], rows: list[str]) -> str:
    return "<div class='wrap'><table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows) + "</table></div>"


def _sect(h: list, n: int, title: str, area: str | None, st: dict, note: str) -> None:
    pill = _vpill("on track" if st[area] == "ok" else VERDICT[st[area]]) if area else ""
    h.append(f"<h2>{n}. {e(title)} {pill}</h2><p class='muted'>{e(note)}</p>")


def _area_table(findings: list[Finding], prefix: str) -> str:
    xs = [f for f in findings if f.code.startswith(prefix)]
    if not xs:
        return "<p class='muted'>Nothing to report.</p>"
    return _table(["Severity", "Finding", "Detail", "Next step"],
                  [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='subj'><b>{e(f.code)}</b> {e(f.subject)}</td>"
                   f"<td class='sm brk'>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td></tr>" for f in xs])


def store_grid(d: Data, rv: dict) -> str:
    g = defaultdict(list)
    for r in store_rows(rv):
        g[r["store"].region].append(r)
    out = ["<p class='legend muted'><span><span class='sw' style='background:var(--r)'></span>red</span><span><span class='sw' "
           "style='background:var(--a)'></span>amber</span><span><span class='sw' style='background:var(--g)'></span>green</span><span><span class='sw' "
           "style='background:var(--n)'></span>opening, refurbishment or closed (framed when it needs action)</span><span>hover a store for the reasons"
           "</span></p><div class='grid'>"]
    for region, rows in sorted(g.items()):
        tr = [r for r in rows if r["store"].trading]
        c = Counter(r["rag"] for r in tr)
        tech = rows[0]["store"].field_tech
        cells = []
        for r in rows:
            x = r["store"]
            cls = r["rag"] if x.trading else "grey"
            style = "" if x.trading or r["rag"] == "green" else f" style='outline:2px solid var(--{'bad' if r['rag'] == 'red' else 'warn'})'"
            tip = f"{x.id} {x.name} · {x.format} · {x.status}" + (f" · {_reasons(r['issues'], 4, x)}" if r["issues"] else "")
            cells.append(f"<span class='cell {cls}'{style} title='{e(tip)}'>{e(x.id.split('-')[-1])}</span>")
        out.append(f"<div class='reg'><h3>{e(region)}</h3><span class='muted'>{e(tech)} · {len(tr)} trading · <b class='critical'>{c.get('red', 0)}"
                   f"</b> red · <b class='warning'>{c.get('amber', 0)}</b> amber · <b class='ok'>{c.get('green', 0)}</b> green</span>"
                   f"<div class='cells'>{''.join(cells)}</div></div>")
    return "".join(out) + "</div>"


def render_html(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s, sm, st = d.settings, summary(d, rv), area_status(findings)
    ov, tr = overall(findings), rv["trend"]
    a, b = tr["window"]
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Week {a:%a %d %b} to {b:%a %d %b}, tickets of the last {s.ticket_days} days · as of {now_label(d.as_of)}</p>",
         f"<span class='overall {'critical' if ov == 'action needed' else 'warning' if ov == 'attention' else 'ok'}'>Overall: {e(ov.upper())}</span>"
         "<div class='tiles'>"]
    tiles = [("Red stores", str(sm["red"]), f"of {sm['trading']} trading · {sm['amber']} amber"),
             ("Visits", str(sm["visits"]), "stores for the field technicians"),
             ("Shipments", str(sm["ships"]), "stores to send something to"),
             ("Vendor calls", str(sm["vendors"] + sm["vendor_estate"]), f"{sm['vendors']} stores, {sm['vendor_estate']} estate-wide"),
             ("Primary lines", pct(sm["uptime"], 2), f"{sm['failovers']} failovers at {sm['on_backup']} stores"),
             ("Backup never tested", str(sm["never_tested"]), f"{sm['no_backup']} stores with no backup line"),
             ("Unsupported Windows", str(sm["unsupported"]), "store and back-office computers"),
             ("Tickets 30 days", str(sm["tickets"]), f"median {sm['median']:g} per store · {sm['past_sla']} past SLA"),
             ("Openings", str(sm["openings"]), f"next {s.opening_weeks} weeks · {sm['closed_pending']} closed with devices out"),
             ("Joiners without account", str(sm["joiners"]), f"next {s.joiner_days} days · {sm['leavers']} leavers enabled")]
    h += [f"<div class='tile'><span class='muted'>{e(x)}</span><b>{e(y)}</b><span class='muted'>{e(z)}</span></div>" for x, y, z in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for ar in AREAS:
        n = sum(f.area == ar and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[ar]}'><span class='lbl'>{e(ar)}</span>{_pill(st[ar], 'ON TRACK' if st[ar] == 'ok' else VERDICT[st[ar]].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div><h2>Stores by region</h2>")
    h.append(store_grid(d, rv))
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2>")
        h.append(_table(["Subject", "What", "Next step", "Owner"],
                        [f"<tr><td class='subj'><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td>"
                         f"<td class='sm brk'>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]))
    # 1 visit and ship list
    h.append("<h2>1. Visit and ship list</h2><p class='muted'>By region and field technician, ranked by severity. Vendor calls are in section 3 "
             "of the pack and in visits.csv.</p>")
    for (region, tech), vs in by_tech(rv):
        vv = [v for v in vs if v["kind"] != "vendor"]
        if not vv:
            continue
        h.append(f"<h3>{e(region)} · {e(tech)}</h3>")
        h.append(_table(["#", "Store", "Status", "Kind", "What", "Why"],
                        [f"<tr><td class='num'>{v['rank']}</td><td class='sm'><b>{e(v['store'].id)}</b> {e(v['store'].name)}<br><span class='muted'>"
                         f"{e(v['store'].format)}</span></td><td>{_pill(v['rag'], v['rag'].upper())}</td><td class='nw'>{e(KIND_LABEL[v['kind']])}</td>"
                         f"<td class='sm'>{e(v['what'])}</td><td class='sm'>{_issues(v['issues'])}</td></tr>" for v in vv]))
    # 2 connectivity
    _sect(h, 2, "Connectivity", "Connectivity", st,
          f"Primary line availability and failovers over the last {s.week_days} days, backup routers and their data plans, the site-to-site tunnel "
          "by store and by region, AnyConnect. connectivity.csv has every store against the previous week.")
    h.append(_table(["Region", "Trading stores", "Tunnel flapping", "Share", "Peak hour"],
                    [f"<tr><td class='nw'><b>{e(g)}</b></td><td class='num'>{x['stores']}</td><td class='num'>{x['flapping']}</td>"
                     f"<td class='num'>{pct(x['share'])}</td><td class='num'>"
                     f"{(lambda hr: f'{hr[0][0]:02d}:00' if hr and x['flapping'] else '–')(x['hours'].most_common(1))}</td></tr>"
                     for g, x in rv["regions"].items()]))
    h.append("<p></p>" + _area_table(findings, "CON"))
    # 3 devices
    _sect(h, 3, "Devices", "Devices", st,
          "Store PCs and back-office computers (Intune and Active Directory), printers (SNMP status and toner), receipt printer jams from the tickets, "
          "card terminals, stock handhelds and UPS. devices-review.csv lists every device.")
    h.append(_area_table(findings, "DEV"))
    # 4 tickets
    _sect(h, 4, "Tickets", "Tickets", st,
          f"Store tickets of the last {s.ticket_days} days against the estate median ({sm['median']:g}), repeat incidents, past SLA (on hold does not "
          "count), field visits and vendor tickets. tickets-review.csv has every ticket.")
    h.append(_area_table(findings, "TKT"))
    # 5 openings
    _sect(h, 5, "Openings and changes", "Openings and changes", st,
          f"Pre-opening checklists for the next {s.opening_weeks} weeks, closing and closed stores, refurbishments. openings.csv has every item.")
    orow = []
    for o in rv["openings"]:
        x = o["store"]
        done = f"{sum(c.done for c in o['items'])} of {len(o['items'])}" if o["items"] else "–"
        orow.append(f"<tr><td class='sm'><b>{e(x.id)}</b> {e(x.name)}<br><span class='muted'>{e(x.format)}</span></td><td class='nw'>{e(o['event'])}</td>"
                    f"<td class='nw sm'>{_t(o['date']) or '–'}</td><td class='num'>{'' if o['days'] is None else o['days']}</td><td class='num'>{done}</td>"
                    f"<td class='sm'>{_issues(o['issues'])}</td></tr>")
    h.append(_table(["Store", "Event", "Date", "Days", "Items done", "Status"], orow))
    # 6 users
    _sect(h, 6, "Users", "Users", st, f"Joiners starting in the next {s.joiner_days} days without an account, leavers still enabled and shared store "
          "accounts of closed stores.")
    h.append(_area_table(findings, "USR"))
    # 7 trend
    h.append("<h2>7. Trend against last week</h2>")
    h.append(_table(["Measure", "This week", "Last week", ""],
                    [f"<tr><td>{e(x)}</td><td class='num'>{e(y)}</td><td class='num'>{e(z)}</td><td class='sm "
                     f"{'critical' if w == 'worse' else 'ok' if w == 'better' else 'muted'}'>{e(w)}</td></tr>" for x, y, z, w in trend_rows(tr)]))
    if tr["has_prev"]:
        h.append(f"<p class='muted'>Red stores (whole estate): {tr['red_now']} this week, {tr['red_prev']} last week. New red: "
                 f"{e(', '.join(tr['new_red']) or 'none')}. Back from red: {e(', '.join(tr['fixed']) or 'none')}.</p>")
    h.append("<h2>All findings</h2>")
    h.append(_table(["Severity", "Area", "Subject", "Detail", "Next step", "Owner"],
                    [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
                     f"<td class='sm brk'>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]))
    h.append("<footer class='muted'>Generated by storehealth. Fictional demo data unless you ran it on your own exports. The weekly pack is "
             "store-review.md.</footer></main></body></html>")
    return "".join(h)


__all__ = ["render_html", "pack_md", "WARNING"]
