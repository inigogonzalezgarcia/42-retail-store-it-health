"""The checks. Every store gets a status from its own issues: red when one is critical, amber when one is a warning, green otherwise. Five
areas: connectivity (primary line availability over the last week, failovers to the 4G/LTE backup router and time on it, backup routers
never tested, data plans near their cap, stores with no backup line, the site-to-site tunnel per store and per region, AnyConnect failures),
devices (store PCs and back-office computers not checked in or on a Windows version out of support, printers offline, low on toner or
jamming, card terminals not reporting, handhelds offline, UPS self-test and battery age), tickets (volume against the estate median,
repeat incidents, past SLA, open field visits, vendor tickets), openings and changes (pre-opening checklists, devices of closed stores,
refurbishments) and users (joiners without an account, leavers still enabled, shared store accounts). Each issue says whether it needs a
visit, a shipment, a vendor call or remote work, which gives the visit and ship list by region and field technician."""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .model import Data, Store, _norm, os_build

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Connectivity", "Devices", "Tickets", "Openings and changes", "Users")
PREFIX = {"CON": "Connectivity", "DEV": "Devices", "TKT": "Tickets", "OPN": "Openings and changes", "USR": "Users"}
VERDICT = {CRITICAL: "action needed", WARNING: "attention", None: "on track"}
RAG = {CRITICAL: "red", WARNING: "amber", None: "green"}
KINDS = ("visit", "ship", "vendor", "remote")


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str
    code: str
    text: str
    store: str = ""
    kind: str = "remote"
    action: str = ""
    n: int = 1

    @property
    def area(self) -> str:
        return PREFIX[self.code[:3]]


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6, sep: str = ", ") -> str:
    return sep.join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def pct(x: float | None, k: int = 0) -> str:
    return "–" if x is None else f"{x:.{k}%}"


def _d(v) -> str:
    return v.strftime("%a %d %b") if v else "never"


def worst(issues) -> str | None:
    sev = {i.severity for i in issues}
    return CRITICAL if CRITICAL in sev else WARNING if WARNING in sev else None


def label(s: Store) -> str:
    return f"{s.id} {s.name}"


def hours_txt(h: float) -> str:
    return f"{h / 24:.0f} days" if h >= 48 else f"{h:.0f} h"


# ---------------------------------------------------------------- connectivity

def week_window(d: Data, back: int = 0) -> tuple[date, date]:
    n = d.settings.week_days
    end = d.today - timedelta(days=1 + back * n)
    return end - timedelta(days=n - 1), end


def conn_metrics(d: Data, days: list) -> dict:
    up = [x.uptime for x in days if x.uptime is not None]
    tun = [x.tunnel_up for x in days if x.tunnel_up is not None]
    return {"days": len(days), "uptime": sum(up) / len(up) if up else None, "failovers": sum(x.failovers for x in days),
            "backup_minutes": sum(x.backup_minutes for x in days), "tunnel_up": sum(tun) / len(tun) if tun else None,
            "tunnel_drops": sum(x.tunnel_drops for x in days), "flap_days": sum(1 for x in days if x.tunnel_drops > 0),
            "drop_hours": Counter(x.tunnel_hour for x in days if x.tunnel_drops and x.tunnel_hour is not None),
            "anyconnect": sum(x.anyconnect for x in days)}


def check_connectivity(d: Data, rv: dict) -> None:
    s = d.settings
    a, b = week_window(d)
    pa, pb = week_window(d, 1)
    by = defaultdict(list)
    for x in d.conn:
        by[x.store].append(x)
    rows = {}
    for st in d.stores:
        days = sorted(by.get(st.id, []), key=lambda x: x.day)
        wk = [x for x in days if a <= x.day <= b]
        prev = [x for x in days if pa <= x.day <= pb]
        last = days[-1] if days else None
        m = conn_metrics(d, wk)
        m.update(prev=conn_metrics(d, prev), last=last, backup_test=last.backup_test if last else None,
                 data_used=last.data_used if last else None, data_cap=last.data_cap if last else None, issues=[])
        m["data_share"] = m["data_used"] / m["data_cap"] if m["data_used"] is not None and m["data_cap"] else None
        rows[st.id] = m
        if not st.trading or not wk:
            continue
        iss = m["issues"]
        L = label(st)
        down_now = last and last.day == b and last.uptime is not None and last.uptime < 0.05
        if down_now:
            run = 0
            for x in reversed(days):
                if x.uptime is not None and x.uptime < 0.05:
                    run += 1
                else:
                    break
            iss.append(Issue(CRITICAL, "CON-01", f"{L}: primary line down for {_n(run, 'day')}, trading on the backup router"
                             + ("" if st.has_backup else " (no backup line)"), st.id, "vendor", "Telco fault ticket; escalate"))
        elif m["uptime"] is not None and m["uptime"] < s.uptime_warning:
            sev = CRITICAL if m["uptime"] < s.uptime_critical else WARNING
            iss.append(Issue(sev, "CON-01", f"{L}: primary line {pct(m['uptime'], 1)} available over the last {s.week_days} days", st.id, "vendor",
                             "Telco ticket with the outage times"))
        if m["failovers"] >= s.failover_warning or m["backup_minutes"] >= s.backup_minutes_warning:
            sev = CRITICAL if m["failovers"] >= s.failover_critical or m["backup_minutes"] >= s.backup_minutes_critical else WARNING
            iss.append(Issue(sev, "CON-02", f"{L}: {_n(m['failovers'], 'failover')} to the backup router, {m['backup_minutes']:,.0f} min on backup "
                             f"(previous week {m['prev']['failovers']})", st.id, "vendor", "Telco ticket: line stability"))
        if st.has_backup:
            if not m["backup_test"]:
                iss.append(Issue(WARNING, "CON-03", f"{L}: backup router never tested", st.id, "remote", "Schedule a failover test out of hours"))
            elif (d.today - m["backup_test"]).days > s.backup_test_max_days:
                iss.append(Issue(WARNING, "CON-03", f"{L}: backup router last tested {(d.today - m['backup_test']).days} days ago", st.id, "remote",
                                 "Schedule a failover test out of hours"))
            if m["data_share"] is not None and m["data_share"] >= s.data_cap_warning:
                sev = CRITICAL if m["data_share"] >= s.data_cap_critical else WARNING
                iss.append(Issue(sev, "CON-04", f"{L}: backup SIM at {pct(m['data_share'])} of its data cap ({m['data_used']:,.0f} of "
                                 f"{m['data_cap']:,.0f} MB)", st.id, "vendor", "Ask the carrier for a temporary cap increase"))
        else:
            sev = CRITICAL if any(i.code == "CON-01" for i in iss) else WARNING
            iss.append(Issue(sev, "CON-05", f"{L} ({st.format}): no backup line", st.id, "ship", "Ship a 4G/LTE router"))
        flapping = m["flap_days"] >= s.tunnel_flap_days or (m["tunnel_up"] is not None and m["tunnel_up"] < s.tunnel_up_min)
        m["flapping"] = flapping
        if flapping:
            hr = m["drop_hours"].most_common(1)
            when = f", mostly around {hr[0][0]:02d}:00" if hr else ""
            iss.append(Issue(WARNING, "CON-06", f"{L}: site-to-site tunnel dropped on {m['flap_days']} of {len(wk)} days ({m['tunnel_drops']} drops"
                             f"{when}), {pct(m['tunnel_up'], 1)} up", st.id, "remote", "Check the tunnel logs with the network team"))
        if m["anyconnect"] >= s.anyconnect_warning:
            iss.append(Issue(WARNING, "CON-08", f"{L}: {m['anyconnect']} failed AnyConnect connections from the back-office laptops", st.id, "remote",
                             "Check the client certificate and profile on the laptops"))
        rv["stores"][st.id]["issues"] += iss
    rv["conn"] = rows
    # region pattern
    reg = defaultdict(list)
    for st in d.stores:
        if st.trading and rows[st.id]["days"]:
            reg[st.region].append(st)
    rv["regions"] = {}
    for region, sts in sorted(reg.items()):
        fl = [x for x in sts if rows[x.id].get("flapping")]
        share = len(fl) / len(sts)
        hours = sum((rows[x.id]["drop_hours"] for x in fl), Counter())
        rv["regions"][region] = {"stores": len(sts), "flapping": len(fl), "share": share, "hours": hours}
        if fl and share >= s.region_flap_share and len(fl) >= 2:
            peak = hours.most_common(1)[0][0] if hours else None
            in_hours = peak is not None and sum(1 for x in fl if x.hours[0] <= peak < x.hours[1]) >= len(fl) / 2
            when = f"; drops peak around {peak:02d}:00" + (", inside trading hours" if in_hours else ", after closing") if peak is not None else ""
            rv["estate"].append(Issue(CRITICAL if in_hours else WARNING, "CON-07",
                                      f"{region}: the tunnel flaps at {len(fl)} of {len(sts)} stores ({pct(share)}){when}", "", "vendor",
                                      "Network team and carrier: head-office concentrator, the region's ISP or a scheduled job", len(fl)))


# ---------------------------------------------------------------- devices

def check_devices(d: Data, rv: dict) -> None:
    s, now = d.settings, d.as_of
    ids = d.by_id
    rows = []
    for dev in sorted(d.devices, key=lambda x: (x.store, x.kind, x.name)):
        st = ids.get(dev.store)
        k = dev.kind
        row = {"dev": dev, "store": st, "issues": [], "age_h": (now - dev.last_sync).total_seconds() / 3600 if dev.last_sync else None,
               "os_end": None}
        rows.append(row)
        if not st or not st.trading:
            continue
        L, iss = f"{dev.name} at {label(st)}", row["issues"]
        age = row["age_h"]
        if k in ("pc", "backoffice", "laptop"):
            if age is None or age > s.stale_days * 24:
                visit = age is None or age > s.stale_visit_days * 24
                iss.append(Issue(WARNING, "DEV-01", f"{L} ({dev.role}): not checked in since {_d(dev.last_sync)}", st.id,
                                 "visit" if visit else "remote", "Ask the store to switch it on and connect it" if not visit else "Check it on the next visit"))
            b = os_build(dev.os_version)
            if "windows" in _norm(dev.os) and b:
                end = s.os_end(b)
                row["os_end"] = end
                if end and end < d.today:
                    iss.append(Issue(WARNING, "DEV-02", f"{L} ({dev.role}): {dev.os} build {b}, out of support since {end:%d %b %Y}", st.id, "remote",
                                     "Feature update via Intune, or ship a replacement if the model is not eligible"))
                elif end and (end - d.today).days <= 30:
                    iss.append(Issue(WARNING, "DEV-02", f"{L} ({dev.role}): build {b} reaches end of servicing on {end:%d %b %Y}", st.id, "remote",
                                     "Feature update via Intune before the date"))
        elif k == "terminal":
            if age is None or age > s.terminal_stale_hours:
                iss.append(Issue(CRITICAL, "DEV-07", f"{L}: card terminal not reported since {_d(dev.last_sync)}", st.id, "vendor",
                                 "Call the payment provider; check the store has a working spare"))
        elif k == "handheld":
            if age is None or age > s.handheld_stale_days * 24:
                iss.append(Issue(WARNING, "DEV-08", f"{L}: stock handheld offline since {_d(dev.last_sync)}", st.id,
                                 "ship" if age is None or age > s.stale_days * 24 else "remote", "Charge and re-enrol it; ship a spare if it does not come back"))
        elif k == "ups":
            if "fail" in _norm(dev.health):
                iss.append(Issue(CRITICAL, "DEV-09", f"{L}: UPS {dev.health}", st.id, "ship", "Ship a replacement UPS or battery"))
            elif dev.battery_date and (d.today - dev.battery_date).days > s.ups_battery_years * 365.25:
                iss.append(Issue(WARNING, "DEV-09", f"{L}: UPS battery from {dev.battery_date:%b %Y}, "
                                 f"{(d.today - dev.battery_date).days / 365.25:.1f} years old", st.id, "ship", "Ship a replacement battery"))
        rv["stores"][st.id]["issues"] += iss
    rv["devices"] = rows
    # printers
    prows = []
    jams = defaultdict(list)
    for t in d.tickets:
        if t.opened and t.opened.date() > d.today - timedelta(days=s.ticket_days) and "jam" in _norm(t.category + " " + t.short_description):
            jams[t.store].append(t)
    model_stores = defaultdict(list)
    for p in sorted(d.printers, key=lambda x: (x.store, x.kind, x.name)):
        st = ids.get(p.store)
        age = (now - p.last_seen).total_seconds() / 3600 if p.last_seen else None
        row = {"p": p, "store": st, "issues": [], "age_h": age, "jams": 0}
        prows.append(row)
        if not st or not st.trading:
            continue
        L, iss = f"{p.name} at {label(st)}", row["issues"]
        offline = age is None or age > s.printer_offline_hours or "offline" in _norm(p.status)
        if offline:
            sev = CRITICAL if p.kind == "receipt" else WARNING
            ship = age is None or age > s.printer_ship_hours
            iss.append(Issue(sev, "DEV-03", f"{L} ({p.kind}, {p.model}): offline, last seen {_d(p.last_seen)}"
                             + (f" ({hours_txt(age)})" if age else ""), st.id, "ship" if ship else "remote",
                             "Ship a swap printer" if ship else "Ask the store to check power and cable"))
        if p.toner is not None and p.toner <= s.toner_warning:
            sev = CRITICAL if p.toner <= s.toner_critical else WARNING
            iss.append(Issue(sev, "DEV-04", f"{L} ({p.model}): toner at {pct(p.toner)}", st.id, "ship", "Ship a toner cartridge"))
        if p.kind == "receipt":
            js = [t for t in jams.get(st.id, []) if not t.ci or t.ci == p.name]
            row["jams"] = len(js)
            if len(js) >= s.jam_repeat:
                model_stores[p.model].append(st)
                iss.append(Issue(WARNING, "DEV-05", f"{L} ({p.model}): {len(js)} paper jam tickets in {s.ticket_days} days", st.id, "ship",
                                 "Ship a replacement receipt printer"))
        rv["stores"][st.id]["issues"] += iss
    rv["printers"] = prows
    for model, sts in sorted(model_stores.items()):
        if len(sts) >= s.jam_model_stores:
            total = sum(len([t for t in jams[x.id]]) for x in sts)
            rv["estate"].append(Issue(CRITICAL, "DEV-06", f"{model}: repeated jams at {len(sts)} stores ({', '.join(x.id for x in sts)}), {total} tickets",
                                      "", "vendor", "Printer vendor: batch, firmware or paper roll spec", len(sts)))


# ---------------------------------------------------------------- tickets

def check_tickets(d: Data, rv: dict) -> None:
    s, now = d.settings, d.as_of
    since = now - timedelta(days=s.ticket_days)
    ids = d.by_id
    recent = [t for t in d.tickets if t.opened and t.opened >= since]
    per = Counter(t.store for t in recent)
    trading = [x for x in d.stores if x.trading]
    counts = [per.get(x.id, 0) for x in trading]
    med = statistics.median(counts) if counts else 0
    rv["ticket_median"] = med
    rows = {}
    for st in d.stores:
        ts = [t for t in recent if t.store == st.id]
        cats = Counter(t.category for t in ts)
        rows[st.id] = {"tickets": len(ts), "ratio": len(ts) / med if med else None, "cats": cats, "open": sum(t.is_open for t in ts),
                       "visits": sum(t.field_visit for t in ts), "vendor_open": sum(1 for t in d.tickets if t.store == st.id and t.is_open and t.vendor)}
        if not st.trading:
            continue
        L, iss = label(st), []
        r = rows[st.id]["ratio"]
        if med and r and len(ts) >= s.ticket_min and r >= s.ticket_ratio_warning:
            top, n = cats.most_common(1)[0]
            iss.append(Issue(CRITICAL if r >= s.ticket_ratio_critical else WARNING, "TKT-01",
                             f"{L}: {len(ts)} tickets in {s.ticket_days} days, {r:.1f}x the estate median of {med:g}; {n} of them '{top}'", st.id,
                             "visit", "Field visit to find the root cause; open a problem record"))
        for cat, n in sorted(cats.items()):
            if n >= s.repeat_count and "jam" not in _norm(cat):
                iss.append(Issue(WARNING, "TKT-02", f"{L}: '{cat}' {n} times in {s.ticket_days} days", st.id, "remote", "Open a problem record"))
        rv["stores"][st.id]["issues"] += iss
    trows = []
    for t in sorted(d.tickets, key=lambda t: (t.store, t.opened or datetime.min, t.number)):
        st = ids.get(t.store)
        sla = float(s.sla_hours.get(str(t.priority), 120))
        age = (now - t.opened).total_seconds() / 3600 if t.opened else 0
        paused = any(w in _norm(t.state) for w in ("hold", "awaiting", "pending vendor"))
        row = {"t": t, "store": st, "sla": sla, "age_h": age, "past_sla": t.is_open and not paused and age > sla, "paused": paused, "issues": []}
        trows.append(row)
        if not t.is_open or not st:
            continue
        L = f"{t.number} at {label(st)}"
        if row["past_sla"]:
            row["issues"].append(Issue(CRITICAL if t.priority <= 2 else WARNING, "TKT-03", f"{L} (P{t.priority}, {t.category}): open {hours_txt(age)}, "
                                       f"SLA {hours_txt(sla)}", st.id, "remote", "Escalate with the resolver group"))
        if t.field_visit:
            row["issues"].append(Issue(WARNING, "TKT-04", f"{L}: field visit pending for '{t.short_description or t.category}'", st.id, "visit",
                                       "Book the visit"))
        if t.vendor and age > s.vendor_open_days * 24:
            telco = any(w in _norm(t.vendor + " " + t.category) for w in ("telco", "line", "carrier", "network", "isp"))
            sev = CRITICAL if telco and any(i.code in ("CON-01", "CON-02") for i in rv["stores"][st.id]["issues"]) else WARNING
            row["issues"].append(Issue(sev, "TKT-05", f"{L}: {t.vendor} ticket {t.vendor_ref or '(no ref)'} open {hours_txt(age)} ({t.category})",
                                       st.id, "vendor", f"Chase {t.vendor}"))
        rv["stores"][st.id]["issues"] += row["issues"]
    rv["tickets"] = rows
    rv["ticket_rows"] = trows


# ---------------------------------------------------------------- openings and changes

LINE = re.compile(r"line install|linea instal|circuit install|line live", re.I)


def check_openings(d: Data, rv: dict) -> None:
    s, today = d.settings, d.today
    horizon = today + timedelta(weeks=s.opening_weeks)
    ids = d.by_id
    ev = defaultdict(list)
    for c in d.checklist:
        ev[(c.store, c.event)].append(c)
    for st in d.stores:
        if st.status == "opening" and (st.id, "opening") not in ev:
            ev[(st.id, "opening")] = []
        if st.status in ("closed", "closing") and (st.id, "closing") not in ev:
            ev[(st.id, "closing")] = []
        if st.status == "refurbishment" and not any(k[0] == st.id for k in ev):
            ev[(st.id, "refurbishment")] = []
    rows = []
    for (sid, kind), items in sorted(ev.items()):
        st = ids.get(sid)
        if not st:
            continue
        when = next((c.date for c in items if c.date), None) or (st.opening_date if "open" in kind else st.closing_date)
        L = label(st)
        row = {"store": st, "event": kind, "date": when, "items": sorted(items, key=lambda c: (c.due or date.max, c.item)), "issues": [],
               "days": (when - today).days if when else None}
        rows.append(row)
        iss = row["issues"]
        if kind.startswith("open"):
            if not when or when < today or when > horizon:
                continue
            todo = [c for c in items if not c.done]
            late = [c for c in todo if c.due and c.due < today]
            blocked = [c for c in todo if c.blocked]
            line = [c for c in todo if LINE.search(c.item)]
            days = row["days"]
            if line and days <= s.opening_critical_days:
                c = line[0]
                iss.append(Issue(CRITICAL, "OPN-01", f"{L}: {st.format} opening {when:%a %d %b} (in {days} days), {c.item.lower()} not done"
                                 + (f" ({c.status.lower()}: {c.notes})" if c.notes else f" ({c.status.lower()})"), sid, "vendor",
                                 "Escalate the line with the carrier and the host; ship a 4G router as the contingency"))
            others = []
            for c in late + blocked:
                if c not in line and all(c is not o for o in others):
                    others.append(c)
            if others:
                sev = CRITICAL if days <= 7 else WARNING
                iss.append(Issue(sev, "OPN-01", f"{L}: opening {when:%a %d %b}, " + "; ".join(
                    f"{c.item.lower()} {'blocked' if c.blocked else 'overdue since ' + c.due.strftime('%d %b')}" for c in others),
                    sid, "remote", "Chase the owners in the openings call"))
            if not iss:
                iss.append(Issue(INFO, "OPN-01", f"{L}: opening {when:%a %d %b}, {len(items) - len(todo)} of {len(items)} items done, none overdue", sid))
        elif kind.startswith("clos"):
            devs = [x for x in d.devices if x.store == sid]
            rec = [c for c in items if re.search(r"recover|collect|recog", c.item, re.I)]
            pending = devs if (not rec or not all(c.done for c in rec)) else []
            row["devices"] = devs
            if st.status == "closed" and pending:
                iss.append(Issue(CRITICAL, "OPN-02", f"{L}: closed on {_d(when)}, {_n(len(pending), 'device')} not recovered ("
                                 + ", ".join(f"{k} {v}" for k, v in sorted(Counter(x.role for x in pending).items())) + ")", sid, "visit",
                                 "Collect them (visit or courier pick-up) and wipe or retire them in Intune", len(pending)))
            elif st.status == "closing" and when and when <= horizon:
                iss.append(Issue(INFO, "OPN-02", f"{L}: closing {when:%a %d %b}, {_n(len(devs), 'device')} to recover", sid, "visit"))
            for c in items:
                if not c.done and c.due and c.due < today and c not in rec:
                    iss.append(Issue(WARNING, "OPN-02", f"{L}: {c.item.lower()} overdue since {c.due:%d %b}", sid, "vendor" if "line" in c.item.lower()
                                     else "remote", f"Chase {c.owner or 'the owner'}"))
        else:
            end = next((c.due for c in items if c.due), None)
            iss.append(Issue(INFO, "OPN-03", f"{L}: in refurbishment" + (f" until {end:%d %b}" if end else "")
                             + "; its devices and printers are not checked until it reopens", sid))
        rv["stores"][sid]["issues"] += iss
    rv["openings"] = rows


# ---------------------------------------------------------------- users

def check_users(d: Data, rv: dict) -> None:
    s, today = d.settings, d.today
    ids = d.by_id
    by_emp = {a.employee_id: a for a in d.accounts if a.employee_id}
    rows = []
    for p in sorted(d.staff, key=lambda p: (p.store, p.start or date.min, p.name)):
        acc = by_emp.get(p.employee_id)
        st = ids.get(p.store)
        L = f"{p.name} ({p.role}) at {label(st) if st else p.store}"
        row = {"p": p, "acc": acc, "store": st, "issues": []}
        rows.append(row)
        if p.start and today <= p.start <= today + timedelta(days=s.joiner_days) and (not acc or not acc.enabled):
            sev = CRITICAL if (p.start - today).days <= 1 else WARNING
            row["issues"].append(Issue(sev, "USR-01", f"{L} starts {p.start:%a %d %b} with no {'enabled ' if acc else ''}account", p.store, "remote",
                                       "Create the account today (network, email, business apps)"))
        if p.end and p.end < today - timedelta(days=s.leaver_grace_days) and acc and acc.enabled:
            row["issues"].append(Issue(WARNING, "USR-02", f"{L} left on {p.end:%d %b}, account {acc.upn} still enabled "
                                       f"({(today - p.end).days} days)", p.store, "remote", "Disable it and run the leaver checklist"))
        if p.store in rv["stores"]:
            rv["stores"][p.store]["issues"] += row["issues"]
        else:
            rv["estate"] += row["issues"]
    shared = [a for a in d.accounts if re.search(s.shared_account_match, a.upn, re.I) and not a.employee_id]
    for a in sorted(shared, key=lambda a: a.upn):
        st = ids.get(a.store)
        if a.enabled and (not st or st.status == "closed"):
            iss = Issue(WARNING, "USR-03", f"{a.upn}: shared account of {'closed store ' + label(st) if st else 'unknown store ' + (a.store or '?')} "
                        "still enabled", a.store, "remote", "Disable it")
            (rv["stores"][a.store]["issues"] if st else rv["estate"]).append(iss)
    rv["users"] = rows
    rv["shared"] = shared


# ---------------------------------------------------------------- review

def review(d: Data) -> dict:
    rv = {"stores": {st.id: {"store": st, "issues": []} for st in d.stores}, "estate": []}
    check_connectivity(d, rv)
    check_devices(d, rv)
    check_tickets(d, rv)
    check_openings(d, rv)
    check_users(d, rv)
    for r in rv["stores"].values():
        r["issues"].sort(key=lambda i: (ORDER[i.severity], i.code, i.text))
        r["severity"] = worst(r["issues"])
        r["rag"] = RAG[r["severity"]]
        r["prev"] = d.previous.get(r["store"].id, "")
    rv["visits"] = visit_list(d, rv)
    rv["trend"] = trend(d, rv)
    return rv


def visit_list(d: Data, rv: dict) -> list[dict]:
    out = []
    for sid, r in rv["stores"].items():
        st = r["store"]
        for kind in ("visit", "ship", "vendor"):
            xs = [i for i in r["issues"] if i.kind == kind and i.severity != INFO]
            if not xs:
                continue
            out.append({"store": st, "kind": kind, "severity": worst(xs), "issues": xs, "rag": r["rag"],
                        "what": "; ".join(dict.fromkeys(i.action for i in xs if i.action))})
    out.sort(key=lambda v: (v["store"].region, v["store"].field_tech, ORDER[v["severity"]], KINDS.index(v["kind"]), -len(v["issues"]), v["store"].id))
    rank = Counter()
    for v in out:
        key = (v["store"].region, v["store"].field_tech)
        if v["kind"] != "vendor":
            rank[key] += 1
        v["rank"] = rank[key] if v["kind"] != "vendor" else ""
    return out


def trend(d: Data, rv: dict) -> dict:
    tr = [x for x in d.stores if x.trading]
    cur = [rv["conn"][x.id] for x in tr if rv["conn"][x.id]["days"]]
    prev = [m["prev"] for m in cur]

    def agg(ms):
        up = [m["uptime"] for m in ms if m["uptime"] is not None]
        return {"uptime": sum(up) / len(up) if up else None, "failovers": sum(m["failovers"] for m in ms),
                "stores_failover": sum(1 for m in ms if m["failovers"]), "backup_minutes": sum(m["backup_minutes"] for m in ms),
                "tunnel_drops": sum(m["tunnel_drops"] for m in ms)}
    a, b = week_window(d)
    pa, pb = week_window(d, 1)
    n = d.settings.week_days
    tk = lambda lo, hi: [t for t in d.tickets if t.opened and lo <= t.opened.date() <= hi]
    now_t, prev_t = tk(a, b), tk(pa, pb)
    out = {"window": (a, b), "prev_window": (pa, pb), "now": agg(cur), "prev": agg(prev)}
    out["now"].update(tickets=len(now_t), visits=sum(t.field_visit for t in now_t))
    out["prev"].update(tickets=len(prev_t), visits=sum(t.field_visit for t in prev_t))
    rows = rv["stores"].values()
    out["red_now"] = sum(r["rag"] == "red" for r in rows)
    out["has_prev"] = bool(d.previous)
    out["red_prev"] = sum(1 for v in d.previous.values() if v == "red")
    out["amber_prev"] = sum(1 for v in d.previous.values() if v == "amber")
    out["new_red"] = sorted(r["store"].id for r in rows if r["rag"] == "red" and r["prev"] and r["prev"] != "red")
    out["fixed"] = sorted(r["store"].id for r in rows if r["prev"] == "red" and r["rag"] != "red")
    out["days"] = n
    return out


# ---------------------------------------------------------------- findings

CODES = {
    "CON-01": ("connectivity", "stores with the primary line down or below target",
               "Open or chase the telco ticket with the outage times; a store on its backup for days is one failure away from not selling.", "store"),
    "CON-02": ("connectivity", "stores failing over to the backup router",
               "Telco ticket for line stability; check the router logs for the cause (line, power, the store's own equipment).", "store"),
    "CON-03": ("connectivity", "backup routers not tested",
               "Test the failover out of trading hours (pull the primary or shut its interface) and record the date; an untested backup is a hope.", "store"),
    "CON-04": ("connectivity", "backup SIMs near their data cap", "Ask the carrier for a temporary increase now, before the router is throttled.",
               "store"),
    "CON-05": ("connectivity", "stores with no backup line", "Ship a 4G/LTE router; for corners, agree with the host where it can sit.", "store"),
    "CON-06": ("connectivity", "stores whose site-to-site tunnel drops",
               "Check the tunnel logs at both ends (rekey, DPD, the ISP) with the network team.", "store"),
    "CON-07": ("connectivity", "a region whose tunnels drop at the same time",
               "One cause for many stores: the head-office concentrator, the region's ISP or a scheduled job. Open one ticket, not one per store.",
               "region"),
    "CON-08": ("connectivity", "stores with failed AnyConnect connections", "Check the client certificate, profile and version on the laptops.",
               "store"),
    "DEV-01": ("devices", "store and back-office computers not checked in",
               "Ask the store to switch them on and connect them; on the next visit if it stays silent.", "device"),
    "DEV-02": ("devices", "store and back-office computers on Windows out of support",
               "Feature update via Intune; ship a replacement where the model is not eligible.", "device"),
    "DEV-03": ("devices", "printers offline", "Ask the store to check power and cable; ship a swap printer after two days.", "printer"),
    "DEV-04": ("devices", "printers low on toner", "Ship the cartridges with the next delivery to the store.", "printer"),
    "DEV-05": ("devices", "receipt printers jamming repeatedly", "Ship a replacement printer; send the old one to the vendor.", "printer"),
    "DEV-06": ("devices", "a receipt printer model jamming at several stores",
               "Vendor call: batch, firmware or paper roll specification. One model, one fix.", "model"),
    "DEV-07": ("devices", "card terminals not reporting", "Call the payment provider today; make sure the store has a working terminal.",
               "terminal"),
    "DEV-08": ("devices", "stock handhelds offline", "Charge and re-enrol them; ship a spare before the next stock count.", "handheld"),
    "DEV-09": ("devices", "UPS failed or old batteries", "Ship the UPS or battery; a failed UPS turns a power blip into a reboot of the store.",
               "UPS"),
    "TKT-01": ("tickets", "stores with many more tickets than the median",
               "One visit to fix the cause beats ten remote fixes: send the field technician with the ticket history.", "store"),
    "TKT-02": ("tickets", "repeat incidents in one store", "Open a problem record per store and category.", "store"),
    "TKT-03": ("tickets", "tickets open past SLA", "Escalate with the resolver group and tell the store manager when to expect it.", "ticket"),
    "TKT-04": ("tickets", "field visits pending", "Book them with the technician of the region (visits.csv).", "ticket"),
    "TKT-05": ("tickets", "vendor tickets open", "Chase the vendor with the reference; escalate the telco ones for stores on backup.", "ticket"),
    "OPN-01": ("openings", "openings in the next weeks", "Chase the overdue items in the openings call; the line is the one with the longest lead time.",
               "store"),
    "OPN-02": ("openings", "closing and closed stores", "Collect the devices, wipe or retire them in Intune, cancel the line and disable the accounts.",
               "store"),
    "OPN-03": ("openings", "stores in refurbishment", "No action: checked again when they reopen.", "store"),
    "USR-01": ("users", "new store staff without an account", "Create the accounts today: network, email and the business apps.", "person"),
    "USR-02": ("users", "leavers still enabled", "Disable them and run the leaver checklist; the access review covers the rest.", "person"),
    "USR-03": ("users", "shared store accounts", "Disable the accounts of closed stores; keep one shared account per store, owned by the store manager.",
               "account"),
}


def all_issues(rv: dict) -> list[Issue]:
    out = [i for r in rv["stores"].values() for i in r["issues"]] + rv["estate"]
    return sorted(out, key=lambda i: (ORDER[i.severity], i.code, i.store, i.text))


def run_all(d: Data, rv: dict | None = None) -> list[Finding]:
    rv = rv if rv is not None else review(d)
    s = d.settings
    hits = defaultdict(list)
    for i in all_issues(rv):
        hits[i.code].append(i)
    out: list[Finding] = []
    for code, (owner, subject, fix, word) in CODES.items():
        for sev in (CRITICAL, WARNING, INFO):
            xs = list({i.text: i for i in hits.get(code, []) if i.severity == sev}.values())
            if not xs:
                continue
            if word == "store":
                head = _n(len({i.store for i in xs}), "store")
            elif word in ("region", "model"):
                head = _n(len(xs), word)
            else:
                head = _n(len(xs), word, {"UPS": "UPS", "person": "people"}.get(word))
            subj = f"{head}: {subject}" if sev != INFO else f"{head} for information ({code}): {subject}"
            out.append(Finding(sev, PREFIX[code[:3]], code, subj, _top([i.text for i in xs], 6, "; "),
                               fix if sev != INFO else "No action now; on the agenda of the weekly review.", s.owner(owner),
                               [i.store or i.text.split(":")[0] for i in xs]))
    sm = summary(d, rv)
    out.append(Finding(INFO, "Connectivity", "MET-01", f"{sm['trading']} trading stores: {sm['red']} red, {sm['amber']} amber, {sm['green']} green",
                       f"{sm['visits']} visits, {sm['ships']} shipments and {sm['vendors']} vendor calls; {sm['openings']} openings in the next "
                       f"{s.opening_weeks} weeks", "Review at the weekly retail operations meeting.", s.owner("tickets")))
    out.sort(key=lambda f: (ORDER[f.severity], AREAS.index(f.area), f.code))
    return out


def summary(d: Data, rv: dict) -> dict:
    rows = list(rv["stores"].values())
    tr = [r for r in rows if r["store"].trading]
    vk = Counter(v["kind"] for v in rv["visits"])
    cm = [rv["conn"][r["store"].id] for r in tr if rv["conn"][r["store"].id]["days"]]
    up = [m["uptime"] for m in cm if m["uptime"] is not None]
    return dict(
        stores=len(rows), trading=len(tr), red=sum(r["rag"] == "red" for r in tr), amber=sum(r["rag"] == "amber" for r in tr),
        green=sum(r["rag"] == "green" for r in tr), visits=vk.get("visit", 0), ships=vk.get("ship", 0), vendors=vk.get("vendor", 0),
        vendor_estate=sum(1 for i in rv["estate"] if i.kind == "vendor"),
        openings=sum(1 for o in rv["openings"] if o["event"].startswith("open") and o["days"] is not None
                     and 0 <= o["days"] <= d.settings.opening_weeks * 7),
        closed_pending=sum(1 for o in rv["openings"] if o["event"].startswith("clos") and any(i.severity == CRITICAL for i in o["issues"])),
        refurb=sum(1 for r in rows if r["store"].status == "refurbishment"),
        uptime=sum(up) / len(up) if up else None, failovers=sum(m["failovers"] for m in cm), on_backup=sum(1 for m in cm if m["failovers"]),
        never_tested=sum(1 for i in all_issues(rv) if i.code == "CON-03" and "never" in i.text),
        no_backup=sum(1 for r in tr if not r["store"].has_backup),
        unsupported=sum(1 for r in rv["devices"] for i in r["issues"] if i.code == "DEV-02" and "out of support" in i.text),
        tickets=sum(rv["tickets"][r["store"].id]["tickets"] for r in tr), median=rv["ticket_median"],
        past_sla=sum(1 for r in rv["ticket_rows"] if r["past_sla"]), vendor_open=sum(1 for t in d.tickets if t.is_open and t.vendor),
        joiners=sum(1 for r in rv["users"] for i in r["issues"] if i.code == "USR-01"),
        leavers=sum(1 for r in rv["users"] for i in r["issues"] if i.code == "USR-02"),
        regions=sorted({r["store"].region for r in rows}),
    )


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st


def overall(findings: list[Finding]) -> str:
    st = set(area_status(findings).values())
    return VERDICT[CRITICAL] if CRITICAL in st else VERDICT[WARNING] if WARNING in st else VERDICT[None]


def now_label(when: datetime) -> str:
    return f"{when:%a %d %b %Y}"


__all__ = ["AREAS", "CRITICAL", "WARNING", "INFO", "Finding", "Issue", "review", "run_all", "summary", "area_status", "overall"]
