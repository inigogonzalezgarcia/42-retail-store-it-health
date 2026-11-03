"""Fictional demo: Northwind Optics, a made-up eyewear chain with 122 stores in Spain and Portugal (street stores, shopping centres and
corners inside department stores), looked after by a central IT team and six field technicians, with no IT staff in the stores. Reviewed on
Tuesday 3 November 2026 with the last two weeks of connectivity and thirty days of tickets. Every store, device, ticket and person is made
up, and the problems are placed on purpose among the everyday ones; faults attributed to printer models are invented."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ORG = "Northwind Optics"
AS_OF = datetime(2026, 11, 3, 8, 0)
TODAY = AS_OF.date()
SEED = 42
DOMAIN = "northwindoptics.example"
HOST = "Galerías Adatum"

SETTINGS = {
    "organisation": ORG,
    "as_of": "2026-11-03 08:00",
    "week_days": 7,
    "ticket_days": 30,
    "uptime_warning": 0.99,
    "uptime_critical": 0.95,
    "failover_warning": 3,
    "failover_critical": 6,
    "backup_minutes_warning": 240,
    "backup_minutes_critical": 1440,
    "backup_test_max_days": 90,
    "data_cap_warning": 0.8,
    "data_cap_critical": 0.9,
    "tunnel_up_min": 0.995,
    "tunnel_flap_days": 4,
    "region_flap_share": 0.5,
    "anyconnect_warning": 5,
    "stale_days": 7,
    "stale_visit_days": 21,
    "terminal_stale_hours": 24,
    "handheld_stale_days": 3,
    "printer_offline_hours": 12,
    "printer_ship_hours": 48,
    "toner_warning": 0.15,
    "toner_critical": 0.05,
    "ups_battery_years": 4,
    "jam_repeat": 3,
    "jam_model_stores": 3,
    "ticket_ratio_warning": 3,
    "ticket_ratio_critical": 4,
    "ticket_min": 8,
    "repeat_count": 3,
    "vendor_open_days": 3,
    "sla_hours": {"1": 4, "2": 8, "3": 72, "4": 120},
    "opening_weeks": 4,
    "opening_critical_days": 14,
    "joiner_days": 7,
    "leaver_grace_days": 1,
    "shared_account_match": "^store\\.",
    "os_end_of_servicing": {},
    "owners": {"connectivity": "Network team (Rubén Ortega)", "devices": "Store IT support (Clara Benítez)",
               "tickets": "Service desk lead (Pablo Serrano)", "openings": "Store openings coordinator (Nuria Vidal)",
               "users": "Identity and access (Sergio Lozano)"},
}

# region, field technician, country, cities, stores
REGIONS = [
    ("Madrid", "Álvaro Medina", "ES", ["Madrid", "Alcalá de Henares", "Getafe", "Alcobendas", "Las Rozas", "Pozuelo de Alarcón", "Leganés"], 26),
    ("Cataluña", "Marta Puig", "ES", ["Barcelona", "Badalona", "Sabadell", "Girona", "Tarragona", "Lleida", "Terrassa"], 22),
    ("Levante", "Javier Soler", "ES", ["Valencia", "Alicante", "Castellón", "Elche", "Murcia", "Gandía"], 18),
    ("Andalucía", "Rocío Navarro", "ES", ["Sevilla", "Málaga", "Granada", "Córdoba", "Cádiz", "Almería", "Jerez"], 20),
    ("Norte", "Iker Etxeberria", "ES", ["Bilbao", "San Sebastián", "Santander", "Oviedo", "Vitoria", "Pamplona", "Gijón"], 16),
    ("Portugal", "Tiago Moreira", "PT", ["Lisboa", "Porto", "Braga", "Coimbra", "Faro", "Aveiro", "Setúbal"], 18),
]
STREET_ES = ["Centro", "Calle Mayor", "Plaza", "Avenida", "Casco Antiguo", "Ensanche"]
STREET_PT = ["Baixa", "Rua Central", "Praça", "Avenida"]
MALLS = ["C.C. Norte", "C.C. Sur", "C.C. Parque", "C.C. Río", "C.C. Plaza"]
HOURS = {"street": "10:00-21:00", "shopping centre": "10:00-22:00", "department store corner": "10:00-22:00"}

FILES = {
    "stores.csv": ("stores", ["store_id", "name", "region", "city", "country", "format", "status", "opening_date", "closing_date", "field_tech",
                              "opening_hours", "backup_line", "host"]),
    "connectivity.csv": ("conn", ["date", "store_id", "primary_uptime_pct", "backup_minutes", "failovers", "backup_last_test", "data_used_mb",
                                  "data_cap_mb", "tunnel_up_pct", "tunnel_drops", "tunnel_peak_hour", "anyconnect_failures"]),
    "devices.csv": ("dev", ["deviceName", "operatingSystem", "osVersion", "lastSyncDateTime", "model", "manufacturer", "serialNumber", "store_id",
                            "role", "source", "health", "battery_date"]),
    "printers.csv": ("prn", ["printer", "store_id", "type", "model", "ip", "status", "error", "toner_pct", "page_count", "last_seen"]),
    "tickets.csv": ("tkt", ["number", "opened_at", "closed_at", "store_id", "category", "priority", "state", "field_visit", "vendor", "vendor_ref",
                            "short_description", "cmdb_ci"]),
    "openings.csv": ("opn", ["store_id", "event", "date", "item", "owner", "due", "status", "notes"]),
    "staff.csv": ("staff", ["employee_id", "name", "store_id", "role", "start_date", "end_date"]),
    "users.csv": ("users", ["userPrincipalName", "displayName", "employeeId", "accountEnabled", "officeLocation", "createdDateTime"]),
}

CATEGORIES = [("Printer / Toner", 4, "Toner low on the A4 printer"), ("Printer / Offline", 3, "Label printer not printing"),
              ("Network / Wi-Fi", 3, "Wi-Fi slow in the stockroom"), ("PC / Slow", 4, "Store PC very slow in the morning"),
              ("PC / Login", 3, "Cannot sign in to the store PC"), ("Accounts / Password reset", 4, "Password reset for a store user"),
              ("Accounts / New user", 4, "Access for a new optician"), ("Card terminal / Not connecting", 2, "Card terminal not connecting"),
              ("Handheld / Sync", 4, "Stock count not syncing from the handheld"), ("Email", 4, "Shared mailbox not updating"),
              ("Business apps / Appointments", 3, "Appointment app not loading"), ("Business apps / Stock", 3, "Stock enquiry very slow"),
              ("Printer / Paper jam", 3, "Receipt printer jams")]
FIRST = ["Lucía", "Carmen", "Sofía", "Elena", "Paula", "Laura", "Marta", "Irene", "Ana", "Sara", "Daniel", "Hugo", "Pablo", "Diego", "Mario",
         "Adrián", "Raúl", "Jorge", "Inês", "Beatriz", "João", "Rui", "Mariana", "Tomás"]
LAST = ["García", "Martín", "López", "Sánchez", "Romero", "Torres", "Ruiz", "Moreno", "Jiménez", "Gil", "Castro", "Ortiz", "Silva", "Costa",
        "Ferreira", "Almeida", "Pereira", "Vidal", "Molina", "Cano"]


def _t(v) -> str:
    if v is None or v == "":
        return ""
    return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else v.strftime("%Y-%m-%d")


def _at(day: date, h: int, m: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, h, m)


def estate(rnd: random.Random) -> list[dict]:
    stores, k = [], 0
    for region, tech, country, cities, n in REGIONS:
        used = set()
        for j in range(n):
            k += 1
            fmt = rnd.choices(["street", "shopping centre", "department store corner"], [0.5, 0.35, 0.15])[0]
            city = cities[j % len(cities)] if j < len(cities) else rnd.choice(cities)
            for _ in range(20):
                lbl = (f"{HOST} corner" if fmt == "department store corner" else rnd.choice(MALLS) if fmt == "shopping centre"
                       else rnd.choice(STREET_PT if country == "PT" else STREET_ES))
                if (city, lbl) not in used:
                    break
            used.add((city, lbl))
            stores.append({"id": f"NW-{k:03d}", "name": f"{city} {lbl}", "region": region, "city": city, "country": country, "format": fmt,
                           "status": "open", "opening_date": date(2012, 3, 1) + timedelta(days=rnd.randint(0, 4800)), "closing_date": None,
                           "tech": tech, "backup": "4G/LTE router", "host": HOST if fmt == "department store corner" else ""})
    return stores


def pick(stores, region=None, fmt=None, city=None, avoid=()) -> dict:
    for s in stores:
        if ((region is None or s["region"] == region) and (fmt is None or s["format"] == fmt) and (city is None or s["city"] == city)
                and s["id"] not in avoid and s["status"] == "open" and not s.get("plant")):
            return s
    raise LookupError((region, fmt, city))


def plant(rnd: random.Random, stores: list[dict]) -> dict:
    P = {}
    P["failover"] = pick(stores, "Madrid", "shopping centre")
    P["linedown"] = pick(stores, "Norte", "street")
    P["tickets"] = pick(stores, "Andalucía", "street", "Sevilla")
    P["ups"] = pick(stores, "Norte", "shopping centre")
    P["jam"] = [pick(stores, "Madrid", "street"), pick(stores, "Cataluña", "shopping centre"), pick(stores, "Andalucía", "shopping centre")]
    for s in [P["failover"], P["linedown"], P["tickets"], P["ups"]] + P["jam"]:
        s["plant"] = True
    c = pick(stores, "Andalucía", city="Cádiz")
    c.update(status="closed", closing_date=date(2026, 10, 10), plant=True)
    l = pick(stores, "Cataluña", city="Lleida")
    l.update(status="closed", closing_date=date(2026, 10, 24), plant=True)
    P["closed"] = [c, l]
    o = pick(stores, "Norte", city="Oviedo")
    o.update(status="open", closing_date=date(2026, 11, 21), plant=True)
    P["closing"] = o
    g = pick(stores, "Madrid", city="Getafe")
    a = pick(stores, "Levante", city="Alicante")
    for s in (g, a):
        s.update(status="refurbishment", plant=True)
    P["refurb"] = [g, a]
    nxt = len(stores)
    corner = {"id": f"NW-{nxt + 1:03d}", "name": f"Madrid {HOST} Serrano corner", "region": "Madrid", "city": "Madrid", "country": "ES",
              "format": "department store corner", "status": "", "opening_date": date(2026, 11, 13), "closing_date": None, "tech": "Álvaro Medina",
              "backup": "4G/LTE router", "host": HOST, "plant": True}
    braga = {"id": f"NW-{nxt + 2:03d}", "name": "Braga Rua do Souto", "region": "Portugal", "city": "Braga", "country": "PT", "format": "street",
             "status": "", "opening_date": date(2026, 11, 26), "closing_date": None, "tech": "Tiago Moreira", "backup": "4G/LTE router", "host": "",
             "plant": True}
    stores += [corner, braga]
    P["corner"], P["braga"] = corner, braga
    trading = [s for s in stores if s["status"] == "open" and s["closing_date"] is None and not s.get("plant")]
    nob = rnd.sample(trading, 3)
    for s in nob:
        s["backup"] = "none"
    P["no_backup"] = nob
    rest = [s for s in trading if s not in nob]
    P["never_tested"] = rnd.sample(rest, 14)
    P["old_test"] = rnd.sample([s for s in rest if s not in P["never_tested"]], 3)
    P["win10"] = {s["id"] for s in rnd.sample(trading, 22)}
    P["w23h2"] = {s["id"] for s in rnd.sample(trading, 5)}
    others = [s for s in trading if s["region"] != "Levante"]
    P["anyconnect"] = rnd.choice([s for s in others if s["format"] != "department store corner"])
    P["terminal"] = {s["id"] for s in rnd.sample(others, 2)}
    P["handheld"] = {s["id"] for s in rnd.sample(trading, 4)}
    P["stale_pc"] = [s["id"] for s in rnd.sample(trading, 4)]
    P["toner"] = [s["id"] for s in rnd.sample([s for s in trading if s["format"] != "department store corner"], 7)]
    P["old_battery"] = {s["id"] for s in rnd.sample(trading, 5)}
    P["printer_off"] = rnd.sample([s for s in trading if s["format"] != "department store corner"], 2)
    P["past_sla"] = rnd.sample(trading, 5)
    P["visits"] = rnd.sample([s for s in trading if s["region"] != "Andalucía"], 2)
    return P


def connectivity(rnd: random.Random, stores: list[dict], P: dict) -> list[list]:
    rows = []
    days = [TODAY - timedelta(days=k) for k in range(14, 0, -1)]
    flap_from = date(2026, 10, 25)
    for s in stores:
        if s["status"] == "" or (s["closing_date"] and s["closing_date"] <= TODAY):
            continue
        sid = s["id"]
        if s in P["never_tested"] or s["backup"] == "none":
            test = None
        elif s in P["old_test"]:
            test = date(2026, 3, 2) + timedelta(days=rnd.randint(0, 60))
        else:
            test = date(2026, 8, 10) + timedelta(days=rnd.randint(0, 80))
        cap = 20000 if s["format"] != "street" or s is P["linedown"] else rnd.choice([10000, 20000])
        used = rnd.randint(200, 2200)
        for k, day in enumerate(days):
            up, fo, mins = 1.0, 0, 0
            if rnd.random() < 0.03:
                mins = rnd.randint(4, 14)
                fo, up = 1, 1 - mins / 1440
            t_up, drops, hour = round(1 - rnd.random() * 0.0008, 4), 0, ""
            if rnd.random() < 0.03:
                drops, hour = 1, rnd.randint(0, 23)
            ac = 0
            if s is P["failover"] and day >= TODAY - timedelta(days=7):
                fo = [1, 2, 0, 1, 2, 1, 2][day.toordinal() - (TODAY - timedelta(days=7)).toordinal()]
                mins = [95, 260, 0, 140, 410, 120, 425][day.toordinal() - (TODAY - timedelta(days=7)).toordinal()]
                up = 1 - mins / 1440
            if s is P["failover"] and day == TODAY - timedelta(days=9):
                fo, mins, up = 1, 35, 1 - 35 / 1440
            if s is P["linedown"]:
                if day == date(2026, 10, 30):
                    fo, mins, up = 1, 140, 1 - 140 / 1440
                elif day > date(2026, 10, 30):
                    fo, mins, up = 0, 1440, 0.0
            if s["region"] == "Levante" and day >= flap_from and rnd.random() < 0.92:
                drops = rnd.randint(2, 4)
                hour = 20
                t_up = round(1 - drops * rnd.uniform(0.002, 0.004), 4)
            if s is P["anyconnect"] and day >= TODAY - timedelta(days=5) and k % 2 == 0:
                ac = 3
            if s["status"] == "refurbishment" and day >= date(2026, 10, 26):
                up, t_up = 0.0, 0.0
            if s["backup"] == "none":
                mins = 0
            used += rnd.randint(0, 25) + mins // 2
            rows.append([_t(day), sid, f"{up * 100:.2f}", mins, fo, _t(test), used if s["backup"] != "none" else "",
                         cap if s["backup"] != "none" else "", f"{t_up * 100:.2f}", drops, hour, ac])
        if s is P["failover"]:
            for k, row in enumerate(rows[-7:]):
                row[6] = 9800 + k * 1470
    return rows


def devices(rnd: random.Random, stores: list[dict], P: dict) -> list[list]:
    rows = []
    for s in stores:
        if s["status"] == "":
            continue
        sid, code = s["id"], s["id"].replace("-", "")
        closed = s["closing_date"] and s["closing_date"] <= TODAY
        refurb = s["status"] == "refurbishment"

        def seen(lo=1, hi=30):
            if closed:
                return _at(s["closing_date"], 20, rnd.randint(0, 59))
            if refurb:
                return _at(date(2026, 10, 25), 21, rnd.randint(0, 59))
            return AS_OF - timedelta(minutes=rnd.randint(lo * 60, hi * 60))
        ser = lambda p: f"{p}{rnd.randint(100000, 999999)}"
        pcv = "10.0.22631.6060" if sid in P["w23h2"] else "10.0.26100.6899"
        pc_seen = seen()
        if sid in P["stale_pc"]:
            pc_seen = AS_OF - timedelta(days=9 if sid != P["stale_pc"][0] else 26, hours=rnd.randint(1, 20))
        rows.append([f"{code}-PC01", "Windows", pcv, _t(pc_seen), rnd.choice(["HP Elite Mini 800 G9", "Lenovo ThinkCentre M70q Gen 4"]), "",
                     ser("CZC"), sid, "store PC", "Intune", "", ""])
        if sid in P["win10"]:
            rows.append([f"{code}-BO01", "Windows 10 Enterprise", "10.0 (19045)", _t(seen(2, 60)), "HP ProDesk 400 G5", "HP", ser("CZC"), sid,
                         "back-office PC", "Active Directory", "", ""])
        else:
            rows.append([f"{code}-BO01", "Windows", "10.0.26100.6899", _t(seen()), "HP ProDesk 400 G9", "HP", ser("CZC"), sid, "back-office PC",
                         "Intune", "", ""])
        if s["format"] != "department store corner":
            rows.append([f"{code}-LT01", "Windows", "10.0.26200.6899", _t(seen(1, 70)), "Lenovo ThinkPad L14 Gen 4", "LENOVO", ser("PF"), sid,
                         "back-office laptop", "Intune", "", ""])
        hh = seen(1, 20) if sid not in P["handheld"] else AS_OF - timedelta(days=rnd.randint(4, 12))
        rows.append([f"{code}-HH01", "Android", "13", _t(hh), "Zebra TC22", "Zebra Technologies", ser("23"), sid, "stock handheld", "Intune", "", ""])
        for t in range(1 if s["format"] == "department store corner" else 2):
            last = seen(0, 14) if not (sid in P["terminal"] and t == 0) else AS_OF - timedelta(hours=rnd.randint(30, 60))
            rows.append([f"TERM-{code}-{t + 1}", "", "", _t(last), "Countertop card terminal", "", ser("T"), sid, "card terminal",
                         "Payment provider portal", "", ""])
        health = "Self-test failed (replace battery)" if s is P["ups"] else "Self-test passed"
        bat = date(2021, 3, 1) + timedelta(days=rnd.randint(0, 200)) if sid in P["old_battery"] else date(2023, 1, 1) + timedelta(days=rnd.randint(0, 900))
        rows.append([f"UPS-{code}", "", "", _t(seen(0, 2)), "APC Smart-UPS SMT750I", "Schneider Electric", ser("AS"), sid, "UPS", "UPS network card",
                     health, _t(bat)])
    return rows


def printers(rnd: random.Random, stores: list[dict], P: dict) -> list[list]:
    rows = []
    jam_ids = {s["id"] for s in P["jam"]}
    toner = {sid: v for sid, v in zip(P["toner"], [0.12, 0.09, 0.14, 0.11, 0.07, 0.04, 0.03])}
    off = {s["id"]: k for k, s in enumerate(P["printer_off"])}
    for n, s in enumerate(stores):
        if s["status"] == "" or (s["closing_date"] and s["closing_date"] <= TODAY):
            continue
        sid, code = s["id"], s["id"].replace("-", "")
        base = f"10.{20 + REGIONS.index(next(r for r in REGIONS if r[0] == s["region"]))}.{n % 250 + 1}"
        refurb = s["status"] == "refurbishment"

        def last(lo=3, hi=40):
            return _at(date(2026, 10, 25), 21, 10) if refurb else AS_OF - timedelta(minutes=rnd.randint(lo, hi))
        kinds = [("receipt", "Epson TM-T20III" if sid in jam_ids else "Epson TM-T88VI", "RCP", ".31"), ("label", "Zebra ZD421", "LBL", ".32")]
        if s["format"] != "department store corner":
            kinds.append(("A4 multifunction", "HP LaserJet Pro MFP 4102fdw", "MFP", ".33"))
        for kind, model, suf, ip in kinds:
            status, err, ton, seen = "idle", "", "", last()
            if kind.startswith("A4"):
                v = toner.get(sid, rnd.uniform(0.2, 0.95))
                ton = f"{v * 100:.0f}"
                err = "lowToner" if v <= 0.15 else ""
            if sid in off and ((off[sid] == 0 and kind == "label") or (off[sid] == 1 and kind == "receipt")):
                seen = AS_OF - (timedelta(days=3, hours=4) if kind == "label" else timedelta(hours=19))
                status, err = "offline", "offline"
            if refurb:
                status, err = "offline", "offline"
            pages = rnd.randint(20000, 400000) if kind.startswith("A4") else rnd.randint(5000, 90000)
            rows.append([f"{code}-{suf}", sid, kind, model, base + ip, status, err, ton, pages, _t(seen)])
    return rows


def tickets(rnd: random.Random, stores: list[dict], P: dict) -> list[list]:
    raw = []
    start = AS_OF - timedelta(days=30)

    def add(s, cat, pri, desc, opened, closed=None, state="Closed", visit=False, vendor="", vref="", ci=""):
        raw.append([opened, closed, s["id"], cat, pri, state, visit, vendor, vref, desc, ci])
    normal = [c for c in CATEGORIES if c[0] != "Printer / Paper jam"]
    for s in stores:
        if s["status"] != "open":
            continue
        k = rnd.choice([2, 3, 3, 4, 4, 4, 5, 5, 6]) if s is not P["tickets"] else 5
        for cat, pri, desc in rnd.sample(normal, k):
            opened = start + timedelta(minutes=rnd.randint(60, 30 * 24 * 60 - 60 * 60))
            opened = opened.replace(hour=rnd.randint(9, 20))
            if opened > AS_OF - timedelta(hours=30) and rnd.random() < 0.6:
                add(s, cat, pri, desc, opened, state="In Progress")
            else:
                closed = opened + timedelta(hours=rnd.randint(1, 30))
                visit = rnd.random() < 0.06
                vendor = "Payment provider" if cat.startswith("Card") else ""
                add(s, cat, pri, desc, opened, min(closed, AS_OF - timedelta(hours=1)), visit=visit, vendor=vendor,
                    vref=f"PP-{rnd.randint(10000, 99999)}" if vendor else "")
    # the store with four times the median: handhelds losing Wi-Fi in the stockroom
    s = P["tickets"]
    for j in range(12):
        opened = _at(date(2026, 10, 6) + timedelta(days=j * 2 + rnd.randint(0, 1)), rnd.randint(10, 19), rnd.randint(0, 59))
        visit = j == 7
        add(s, "Network / Wi-Fi", 3, "Stock handheld drops Wi-Fi in the stockroom", opened, opened + timedelta(hours=rnd.randint(2, 20)), visit=visit,
            ci=f"{s['id'].replace('-', '')}-HH01")
    add(s, "Network / Wi-Fi", 3, "Handhelds drop Wi-Fi again during the stock count", _at(date(2026, 11, 2), 11, 20), state="In Progress",
        visit=True, ci=f"{s['id'].replace('-', '')}-HH01")
    # receipt printers of one model jamming in three stores
    for s, n in zip(P["jam"], (4, 3, 5)):
        for j in range(n):
            opened = _at(date(2026, 10, 8) + timedelta(days=j * 6 + rnd.randint(0, 3)), rnd.randint(10, 20), rnd.randint(0, 59))
            add(s, "Printer / Paper jam", 3, "Receipt printer jams on every roll change", opened, opened + timedelta(hours=rnd.randint(1, 6)),
                ci=f"{s['id'].replace('-', '')}-RCP")
    j0 = P["jam"][2]
    add(j0, "Printer / Paper jam", 3, "Vendor case: Epson TM-T20III jams across stores", _at(date(2026, 10, 29), 12, 15), state="On Hold",
        vendor="Printer vendor", vref="EPS-778214", ci=f"{j0['id'].replace('-', '')}-RCP")
    # telco tickets
    add(P["failover"], "Network / Line", 3, "Primary line keeps failing over to 4G", _at(date(2026, 10, 28), 18, 40), state="On Hold",
        vendor="Telco", vref="TEL-5520931")
    add(P["linedown"], "Network / Line", 3, "Primary line down, store on 4G backup", _at(date(2026, 10, 30), 22, 5), state="On Hold",
        vendor="Telco", vref="TEL-5523377")
    add(P["corner"], "Network / New line", 4, f"New line for the {HOST} Serrano corner", _at(date(2026, 9, 25), 10, 30), state="On Hold",
        vendor="Telco", vref="TEL-ORD-118402")
    for sid in sorted(P["terminal"]):
        s = next(x for x in stores if x["id"] == sid)
        add(s, "Card terminal / Not connecting", 2, "One card terminal not connecting since Sunday", _at(date(2026, 11, 2), 10, 5),
            state="On Hold", vendor="Payment provider", vref=f"PP-{rnd.randint(10000, 99999)}", ci=f"TERM-{sid.replace('-', '')}-1")
    add(P["ups"], "Power / UPS", 3, "UPS beeping in the back office", _at(date(2026, 11, 1), 10, 40), state="New")
    # past SLA
    for k, s in enumerate(P["past_sla"]):
        if k < 2:
            add(s, "Business apps / Appointments", 2, "Appointment app not loading for the opticians", _at(date(2026, 10, 31), 10 + k, 15),
                state="In Progress")
        else:
            add(s, "PC / Slow", 3, "Back-office PC freezing", _at(date(2026, 10, 26 + k), 12, 30), state="In Progress")
    for s, (cat, desc) in zip(P["visits"], [("PC / Won't boot", "Store PC does not boot"), ("Network / Switch", "Switch in the back office dead")]):
        add(s, cat, 3, desc, _at(date(2026, 11, 2), 9, 50), state="Assigned", visit=True)
    raw.sort(key=lambda r: (r[0], r[2], r[3]))
    rows = []
    for k, r in enumerate(raw):
        opened, closed, sid, cat, pri, state, visit, vendor, vref, desc, ci = r
        rows.append([f"INC{45001 + k:07d}", _t(opened), _t(closed), sid, cat, f"{pri} - {['', 'Critical', 'High', 'Moderate', 'Low'][pri]}", state,
                     "true" if visit else "false", vendor, vref, desc, ci])
    return rows


def checklists(P: dict) -> list[list]:
    c, b, o = P["corner"]["id"], P["braga"]["id"], P["closing"]["id"]
    rows = [
        [c, "opening", "2026-11-13", "Line ordered", "Network team", "2026-09-25", "Done", "Telco order TEL-ORD-118402"],
        [c, "opening", "2026-11-13", "Line installed", "Telco and host IT", "2026-10-30", "Blocked",
         f"The carrier cannot reach the corner until {HOST} patches its floor comms room to it; joint visit with the host's technicians on 10 Nov"],
        [c, "opening", "2026-11-13", "4G/LTE backup router shipped", "Store IT support", "2026-11-06", "Done", ""],
        [c, "opening", "2026-11-13", "Store PC and back-office PC staged", "Store IT support", "2026-11-06", "Done", ""],
        [c, "opening", "2026-11-13", "Printers (receipt, label) installed", "Store IT support", "2026-11-10", "In progress", ""],
        [c, "opening", "2026-11-13", "Card terminal activated", "Payment provider", "2026-11-11", "In progress", ""],
        [c, "opening", "2026-11-13", "Staff accounts created", "Identity and access", "2026-11-06", "Not started", "Four staff start on 10 Nov"],
        [c, "opening", "2026-11-13", "Test day (sale, receipt, card, VPN)", "Field technician", "2026-11-12", "Not started", ""],
        [b, "opening", "2026-11-26", "Line ordered", "Network team", "2026-10-01", "Done", ""],
        [b, "opening", "2026-11-26", "Line installed", "Telco", "2026-11-12", "Done", "Installed 29 Oct"],
        [b, "opening", "2026-11-26", "4G/LTE backup router shipped", "Store IT support", "2026-11-18", "Done", ""],
        [b, "opening", "2026-11-26", "Store PC and back-office PC staged", "Store IT support", "2026-11-18", "Not started", ""],
        [b, "opening", "2026-11-26", "Printers (receipt, label, A4) installed", "Store IT support", "2026-11-20", "Not started", ""],
        [b, "opening", "2026-11-26", "Card terminals activated", "Payment provider", "2026-11-20", "Not started", ""],
        [b, "opening", "2026-11-26", "Staff accounts created", "Identity and access", "2026-11-19", "Not started", ""],
        [b, "opening", "2026-11-26", "Test day (sale, receipt, card, VPN)", "Field technician", "2026-11-25", "Not started", ""],
        [o, "closing", "2026-11-21", "Line cancellation requested", "Network team", "2026-10-31", "Not started", "Twenty days' notice in the contract"],
        [o, "closing", "2026-11-21", "Devices recovered", "Field technician", "2026-11-21", "Not started", ""],
        [o, "closing", "2026-11-21", "Accounts disabled", "Identity and access", "2026-11-21", "Not started", ""],
    ]
    for s, rec, acc in zip(P["closed"], ("Not started", "In progress"), ("Done", "In progress")):
        d = _t(s["closing_date"])
        rows += [[s["id"], "closing", d, "Line cancelled", "Network team", d, "Done", ""],
                 [s["id"], "closing", d, "Devices recovered", "Field technician", d, rec, "Courier pick-up not booked" if rec == "Not started" else
                  "Waiting for the landlord's keys"],
                 [s["id"], "closing", d, "Accounts disabled", "Identity and access", d, acc, ""]]
    for s, end in zip(P["refurb"], ("2026-11-14", "2026-11-20")):
        rows.append([s["id"], "refurbishment", "2026-10-26", "Reopening test (line, printers, card terminals)", "Field technician", end, "Not started", ""])
    return rows


def people(rnd: random.Random, stores: list[dict], P: dict) -> tuple[list[list], list[list]]:
    staff, users = [], []
    trading = [s for s in stores if s["status"] == "open" and not s.get("plant")]
    names = iter(rnd.sample([f"{f} {l}" for f in FIRST for l in LAST], 60))
    eid = iter(range(30410, 30600))

    def person(s, role, start=None, end=None, account=True, enabled=True, created=None):
        n, e = next(names), str(next(eid))
        staff.append([e, n, s["id"], role, _t(start), _t(end)])
        if account:
            upn = n.lower().replace(" ", ".").translate(str.maketrans("áéíóúñêãçô", "aeiounoeac")) + "@" + DOMAIN
            users.append([upn, n, e, "true" if enabled else "false", s["id"], _t(created or _at((start or TODAY) - timedelta(days=5), 9))])
    tomorrow = TODAY + timedelta(days=1)
    j = rnd.sample(trading, 3)
    for s, roles in zip(j, (["Optician", "Sales advisor"], ["Optician", "Store manager"], ["Sales advisor"])):
        for r in roles:
            person(s, r, start=tomorrow, account=not (r == "Optician" and s is not j[1] or r == "Store manager"))
    for r in ("Store manager", "Optician", "Optician", "Sales advisor"):
        person(P["corner"], r, start=date(2026, 11, 10), account=False)
    for s in rnd.sample(trading, 2):
        person(s, "Sales advisor", start=date(2026, 11, 16), account=False)
    for s in rnd.sample(trading, 4):
        person(s, rnd.choice(["Optician", "Sales advisor"]), start=date(2026, 10, 1) + timedelta(days=rnd.randint(0, 25)))
    for s, end, en in zip(rnd.sample(trading, 6), ("2026-09-25", "2026-10-15", "2026-10-24", "2026-10-31", "2026-11-02", "2026-10-20"),
                          (True, True, True, True, True, False)):
        person(s, rnd.choice(["Optician", "Sales advisor", "Store manager"]), start=date(2019, 5, 1) + timedelta(days=rnd.randint(0, 1500)),
               end=date.fromisoformat(end), enabled=en)
    for s in stores:
        if s["status"] == "":
            continue
        users.append([f"store.{s['id'].replace('-', '').lower()}@{DOMAIN}", f"Store {s['id']} {s['name']}", "", "true", s["id"],
                      _t(_at(s["opening_date"], 9))])
    return staff, users


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(SEED)
    stores = estate(rnd)
    P = plant(rnd, stores)
    out = {"stores": [], "conn": connectivity(rnd, stores, P), "dev": devices(rnd, stores, P), "prn": printers(rnd, stores, P),
           "tkt": tickets(rnd, stores, P), "opn": checklists(P)}
    out["staff"], out["users"] = people(rnd, stores, P)
    for s in stores:
        out["stores"].append([s["id"], s["name"], s["region"], s["city"], s["country"], s["format"], s["status"], _t(s["opening_date"]),
                              _t(s["closing_date"]), s["tech"], HOURS[s["format"]], s["backup"], s["host"]])
    for name, (k, header) in FILES.items():
        with open(folder / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(out[k])
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    previous(folder, P, rnd)
    return folder


def previous(folder: Path, P: dict, rnd: random.Random) -> None:
    """Last week's stores.csv: the same estate a week earlier, before the Levante tunnels, the failovers and the line fault started, with a
    few stores that were red and were fixed during the week."""
    from .checks import review
    from .model import load
    prev = folder / "previous-stores.csv"
    if prev.exists():
        prev.unlink()
    rv = review(load(folder))
    rag = {}
    for sid, r in rv["stores"].items():
        codes = {i.code for i in r["issues"] if i.severity == "critical"}
        rag[sid] = "red" if codes & {"TKT-01", "OPN-02", "DEV-04"} else "amber" if r["rag"] != "green" else "green"
    for sid, r in rv["stores"].items():
        codes = {i.code for i in r["issues"] if i.severity != "info"}
        if r["store"].region == "Levante" and codes <= {"CON-06", "CON-03", "CON-07"}:
            rag[sid] = "amber" if "CON-03" in codes else "green"
    for s in (P["failover"], P["linedown"]):
        rag[s["id"]] = "green"
    rag[P["corner"]["id"]] = "amber"
    for s in P["jam"]:
        rag[s["id"]] = "amber"
    greens = sorted(sid for sid, r in rv["stores"].items() if r["rag"] == "green" and r["store"].trading)
    for sid in random.Random(SEED + 1).sample(greens, 3):
        rag[sid] = "red"
    with open(prev, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["store_id", "name", "region", "rag"])
        for sid in sorted(rag):
            w.writerow([sid, rv["stores"][sid]["store"].name, rv["stores"][sid]["store"].region, rag[sid]])
