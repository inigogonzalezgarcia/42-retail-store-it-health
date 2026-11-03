import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from storehealth import cli
from storehealth.checks import CRITICAL, INFO, ORDER, WARNING, area_status, overall, review, run_all, summary
from storehealth.model import (Account, ChecklistItem, ConnDay, Data, Device, Printer, Staff, Store, Ticket, load, load_accounts, load_conn,
                               load_devices, load_printers, load_stores, load_tickets, os_build, settings_from_dict)

AS_OF = datetime(2026, 11, 3, 8, 0)          # Tuesday
TODAY = AS_OF.date()


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def store(sid, region="Madrid", fmt="street", status="open", backup="4G/LTE router", **kw) -> Store:
    return Store(sid, kw.pop("name", f"Store {sid}"), region, kw.pop("city", "Madrid"), "ES", fmt, status, kw.pop("opening_date", date(2020, 1, 1)),
                 kw.pop("closing_date", None), kw.pop("field_tech", "Tech A"), kw.pop("hours", (10, 21)), backup, **kw)


def days(sid, n=14, **kw) -> list[ConnDay]:
    """n quiet days before today; keyword values apply to the last seven."""
    out = []
    for k in range(n, 0, -1):
        day = TODAY - timedelta(days=k)
        x = ConnDay(day, sid, 1.0, 0, 0, date(2026, 10, 1), 500, 20000, 1.0, 0, None, 0)
        if k <= 7:
            for a, v in kw.items():
                setattr(x, a, v(k) if callable(v) else v)
        out.append(x)
    return out


def data(stores=(), conn=(), devices=(), printers=(), tickets=(), checklist=(), staff=(), accounts=(), previous=None, **raw) -> Data:
    return Data(settings_from_dict(raw), AS_OF, list(stores), list(conn), list(devices), list(printers), list(tickets), list(checklist),
                list(staff), list(accounts), previous or {})


def codes(findings, code):
    return [f for f in findings if f.code == code]


def tk(n, sid, opened, cat="PC / Slow", pri=3, state="Closed", closed=None, **kw) -> Ticket:
    return Ticket(f"INC{n:05d}", opened, closed if closed is not None else (opened + timedelta(hours=3) if state == "Closed" else None), sid, cat, pri,
                  state, **kw)


class TestLoading(unittest.TestCase):
    def test_stores_connectivity_and_status_from_dates(self):
        with tempfile.TemporaryDirectory() as t:
            sp = write(Path(t) / "s.csv", ["Store ID", "Name", "Region", "Format", "Status", "Opening date", "Closing date", "Field tech", "Opening hours",
                                           "Backup line"],
                       [["NW-1", "A", "Norte", "street", "", "2015-01-01", "", "T", "10:00-21:00", "4G/LTE router"],
                        ["NW-2", "B", "Norte", "department store corner", "", "2026-11-13", "", "T", "10:00-22:00", "none"],
                        ["NW-3", "C", "Norte", "street", "", "2014-01-01", "10/10/2026", "T", "", ""],
                        ["NW-4", "D", "Norte", "street", "Refurbishment", "2014-01-01", "", "T", "", ""],
                        ["NW-5", "E", "Norte", "street", "", "2014-01-01", "2026-11-21", "T", "", ""]], delimiter=";")
            cp = write(Path(t) / "c.csv", ["date", "store_id", "primary_uptime_pct", "backup_minutes", "failovers", "backup_last_test", "data_used_mb",
                                           "data_cap_mb", "tunnel_up_pct", "tunnel_drops", "tunnel_peak_hour"],
                       [["2026-11-02", "NW-1", "99,5", "7", "1", "", "1200", "20000", "0.997", "2", "20"]])
            st = load_stores(sp, TODAY)
            c = load_conn(cp)[0]
        self.assertEqual([s.status for s in st], ["open", "opening", "closed", "refurbishment", "closing"])
        self.assertEqual((st[0].hours, st[0].has_backup, st[1].has_backup, st[0].trading, st[4].trading), ((10, 21), True, False, True, True))
        self.assertEqual((c.uptime, c.backup_minutes, c.failovers, c.backup_test, c.tunnel_up, c.tunnel_drops, c.tunnel_hour),
                         (0.995, 7, 1, None, 0.997, 2, 20))

    def test_devices_printers_tickets_and_accounts(self):
        with tempfile.TemporaryDirectory() as t:
            dp = write(Path(t) / "d.csv", ["deviceName", "operatingSystem", "osVersion", "lastSyncDateTime", "officeLocation", "role", "health"],
                       [["PC1", "Windows", "10.0.26100.6899", "2026-11-02T22:10:05Z", "NW-1", "store PC", ""],
                        ["BO1", "Windows 10 Enterprise", "10.0 (19045)", "2026-11-01 09:12", "NW-1", "back-office PC", ""],
                        ["UPS1", "", "", "", "NW-1", "UPS", "Self-test failed"], ["T1", "", "", "", "NW-1", "card terminal", ""],
                        ["HH1", "Android", "13", "", "NW-1", "stock handheld", ""]])
            pp = write(Path(t) / "p.csv", ["printer", "store", "type", "model", "hrPrinterStatus", "toner_pct", "last_seen"],
                       [["P1", "NW-1", "receipt", "Epson TM-T88VI", "idle", "", "2026-11-03 07:50"], ["P2", "NW-1", "A4", "HP", "idle", "-3", ""],
                        ["P3", "NW-1", "A4", "HP", "idle", "8", ""]])
            tp = write(Path(t) / "t.csv", ["number", "opened_at", "closed_at", "u_store", "category", "priority", "state", "u_field_visit", "u_vendor"],
                       [["INC1", "2026-11-01 10:00", "", "NW-1", "Printer / Paper jam", "2 - High", "On Hold", "true", "Printer vendor"]])
            up = write(Path(t) / "u.csv", ["userPrincipalName", "employeeId", "accountEnabled", "officeLocation"],
                       [["a@x.example", "100", "False", "NW-1"], ["store.nw1@x.example", "", "True", "NW-1"]])
            dv, pr, ti, ac = load_devices(dp), load_printers(pp), load_tickets(tp)[0], load_accounts(up)
        self.assertEqual([d.kind for d in dv], ["pc", "backoffice", "ups", "terminal", "handheld"])
        self.assertEqual((os_build(dv[0].os_version), os_build(dv[1].os_version), dv[1].last_sync), ("26100", "19045", datetime(2026, 11, 1, 9, 12)))
        self.assertEqual([(p.kind, p.toner) for p in pr], [("receipt", None), ("a4", None), ("a4", 0.08)])
        self.assertEqual((ti.priority, ti.is_open, ti.field_visit, ti.group), (2, True, True, "Printer"))
        self.assertEqual([(a.enabled, a.employee_id) for a in ac], [(False, "100"), (True, "")])


class TestConnectivity(unittest.TestCase):
    def test_line_failovers_data_cap_and_no_backup(self):
        sts = [store("A"), store("B"), store("C", backup="none"), store("D")]
        conn = (days("A", failovers=lambda k: 1 if k != 3 else 2, backup_minutes=200, uptime=1 - 200 / 1440, data_used=18500)
                + days("B", uptime=lambda k: 0.0 if k <= 2 else 1.0, backup_minutes=lambda k: 1440 if k <= 2 else 0)
                + days("C", uptime=0.993) + days("D"))
        f = run_all(data(sts, conn))
        c1 = codes(f, "CON-01")
        self.assertEqual([(x.severity, x.items) for x in c1], [(CRITICAL, ["A", "B"])])
        self.assertIn("primary line down for 2 days", c1[0].detail)
        self.assertEqual(codes(f, "CON-02")[0].items, ["A", "B"])
        self.assertIn("8 failovers", codes(f, "CON-02")[0].detail)
        self.assertEqual((codes(f, "CON-04")[0].severity, codes(f, "CON-04")[0].items), (CRITICAL, ["A"]))
        self.assertEqual([(x.severity, x.items) for x in codes(f, "CON-05")], [(WARNING, ["C"])])
        rv = review(data(sts, conn))
        self.assertEqual((rv["stores"]["D"]["rag"], rv["stores"]["C"]["rag"], rv["stores"]["A"]["rag"]), ("green", "amber", "red"))

    def test_backup_tests_and_regional_tunnel(self):
        sts = [store(f"L{k}", region="Levante", fmt="shopping centre", hours=(10, 22)) for k in range(4)] + [store("M1"), store("M2")]
        conn = []
        for k in range(3):
            conn += days(f"L{k}", tunnel_drops=3, tunnel_hour=20, tunnel_up=0.99)
        conn += days("L3") + days("M1", backup_test=None) + days("M2", backup_test=date(2026, 5, 1))
        for x in conn:
            if x.store == "M1":
                x.backup_test = None
        f = run_all(data(sts, conn))
        c3 = codes(f, "CON-03")[0]
        self.assertEqual(c3.items, ["M1", "M2"])
        self.assertIn("never tested", c3.detail)
        self.assertIn("186 days ago", c3.detail)
        self.assertEqual(codes(f, "CON-06")[0].items, ["L0", "L1", "L2"])
        c7 = codes(f, "CON-07")[0]
        self.assertEqual(c7.severity, CRITICAL)
        self.assertIn("3 of 4 stores (75%)", c7.detail)
        self.assertIn("20:00, inside trading hours", c7.detail)
        late = [store(f"L{k}", region="Levante", hours=(10, 20)) for k in range(4)]
        self.assertEqual(codes(run_all(data(late, conn)), "CON-07")[0].severity, WARNING)


class TestDevices(unittest.TestCase):
    def test_computers_terminals_handhelds_and_ups(self):
        sts = [store("A"), store("Z", status="refurbishment")]
        ago = lambda h: AS_OF - timedelta(hours=h)
        devs = [Device("PC1", "Windows", "10.0.26100.6899", ago(2), store="A", role="store PC"),
                Device("PC2", "Windows", "10.0.26100.6899", ago(24 * 9), store="A", role="store PC"),
                Device("PC3", "Windows", "10.0.26100.6899", ago(24 * 30), store="A", role="store PC"),
                Device("BO1", "Windows 10 Enterprise", "10.0 (19045)", ago(3), store="A", role="back-office PC"),
                Device("BO2", "Windows", "10.0.22631.6060", ago(3), store="A", role="back-office PC"),
                Device("T1", last_sync=ago(30), store="A", role="card terminal"), Device("T2", last_sync=ago(2), store="A", role="card terminal"),
                Device("HH1", "Android", "13", ago(24 * 5), store="A", role="stock handheld"),
                Device("U1", last_sync=ago(1), store="A", role="UPS", health="Self-test failed"),
                Device("U2", last_sync=ago(1), store="A", role="UPS", health="Self-test passed", battery_date=date(2021, 6, 1)),
                Device("ZPC", "Windows", "10.0.26100.6899", ago(24 * 9), store="Z", role="store PC")]
        f = run_all(data(sts, devices=devs))
        d1 = codes(f, "DEV-01")[0]
        self.assertEqual(d1.items, ["A", "A"])
        rv = review(data(sts, devices=devs))
        kinds = {i.text.split(" ")[0]: i.kind for i in rv["stores"]["A"]["issues"]}
        self.assertEqual((kinds["PC2"], kinds["PC3"]), ("remote", "visit"))
        d2 = codes(f, "DEV-02")
        self.assertEqual(len(d2), 1)
        self.assertIn("out of support since 14 Oct 2025", d2[0].detail)
        self.assertIn("reaches end of servicing on 10 Nov 2026", d2[0].detail)
        self.assertEqual((codes(f, "DEV-07")[0].severity, codes(f, "DEV-07")[0].items), (CRITICAL, ["A"]))
        self.assertEqual(codes(f, "DEV-08")[0].severity, WARNING)
        self.assertEqual([x.severity for x in codes(f, "DEV-09")], [CRITICAL, WARNING])
        self.assertEqual(rv["stores"]["Z"]["rag"], "green")

    def test_printers_offline_toner_and_jam_model(self):
        sts = [store(x) for x in "ABCD"]
        seen = lambda h: AS_OF - timedelta(hours=h)
        prs = [Printer("A-RCP", "A", "receipt", "TM-X", last_seen=seen(20)), Printer("A-LBL", "A", "label", "ZD", last_seen=seen(80)),
               Printer("A-MFP", "A", "A4", "MFP", toner=0.04, last_seen=seen(0.2)), Printer("B-MFP", "B", "A4", "MFP", toner=0.12, last_seen=seen(0.2))]
        prs += [Printer(f"{x}-RCP", x, "receipt", "TM-J", last_seen=seen(0.1)) for x in "BCD"]
        tks = [tk(k, x, AS_OF - timedelta(days=k + 1), "Printer / Paper jam", ci=f"{x}-RCP") for x in "BCD" for k in range(3)]
        f = run_all(data(sts, printers=prs, tickets=tks))
        d3 = codes(f, "DEV-03")
        self.assertEqual([(x.severity, x.subject.split(":")[0]) for x in d3], [(CRITICAL, "1 printer"), (WARNING, "1 printer")])
        rv = review(data(sts, printers=prs, tickets=tks))
        kinds = {i.text.split(" ")[0]: i.kind for i in rv["stores"]["A"]["issues"]}
        self.assertEqual((kinds["A-RCP"], kinds["A-LBL"], kinds["A-MFP"]), ("remote", "ship", "ship"))
        self.assertEqual([x.severity for x in codes(f, "DEV-04")], [CRITICAL, WARNING])
        self.assertEqual(codes(f, "DEV-05")[0].items, ["B", "C", "D"])
        d6 = codes(f, "DEV-06")[0]
        self.assertEqual(d6.severity, CRITICAL)
        self.assertIn("TM-J: repeated jams at 3 stores (B, C, D), 9 tickets", d6.detail)
        self.assertFalse(codes(f, "TKT-02"))


class TestTickets(unittest.TestCase):
    def test_volume_repeats_sla_visits_and_vendors(self):
        sts = [store(f"S{k}") for k in range(5)]
        tks, n = [], 0
        for k in range(1, 5):
            for j in range(4):
                n += 1
                tks.append(tk(n, f"S{k}", AS_OF - timedelta(days=j + 2), ["PC / Slow", "Email", "PC / Login", "Accounts"][j]))
        for j in range(20):
            n += 1
            tks.append(tk(n, "S0", AS_OF - timedelta(days=j + 1), "Network / Wi-Fi" if j < 10 else f"Cat {j}"))
        tks += [tk(900, "S1", AS_OF - timedelta(hours=20), pri=2, state="In Progress"),
                tk(901, "S2", AS_OF - timedelta(days=4), pri=3, state="In Progress"),
                tk(902, "S3", AS_OF - timedelta(days=5), "Network / Line", pri=3, state="On Hold", vendor="Telco", vendor_ref="TEL-1"),
                tk(903, "S4", AS_OF - timedelta(hours=5), "PC / Won't boot", state="Assigned", field_visit=True),
                tk(904, "S4", AS_OF - timedelta(days=60), "PC / Slow")]
        d = data(sts, tickets=tks)
        f = run_all(d)
        t1 = codes(f, "TKT-01")[0]
        self.assertEqual((t1.severity, t1.items), (CRITICAL, ["S0"]))
        self.assertIn("20 tickets in 30 days, 4.0x the estate median of 5", t1.detail)
        self.assertIn("10 of them 'Network / Wi-Fi'", t1.detail)
        self.assertEqual(codes(f, "TKT-02")[0].items, ["S0"])
        self.assertEqual([(x.severity, x.items) for x in codes(f, "TKT-03")], [(CRITICAL, ["S1"]), (WARNING, ["S2"])])
        self.assertEqual(codes(f, "TKT-04")[0].items, ["S4"])
        self.assertEqual((codes(f, "TKT-05")[0].severity, codes(f, "TKT-05")[0].items), (WARNING, ["S3"]))
        rv = review(d)
        self.assertFalse(next(r for r in rv["ticket_rows"] if r["t"].number == "INC00902")["past_sla"])
        conn = days("S3", uptime=0.9) + [x for s in ("S0", "S1", "S2", "S4") for x in days(s)]
        self.assertEqual(codes(run_all(data(sts, conn, tickets=tks)), "TKT-05")[0].severity, CRITICAL)


class TestOpeningsAndUsers(unittest.TestCase):
    def test_opening_checklist_closed_store_and_refurbishment(self):
        corner = store("C", fmt="department store corner", opening_date=date(2026, 11, 13))
        far = store("F", opening_date=date(2026, 11, 26))
        closed = store("X", closing_date=date(2026, 10, 10))
        refurb = store("R", status="refurbishment")
        sts = [store("A")] + [load_stores_status(x) for x in (corner, far, closed, refurb)]
        items = [ChecklistItem("C", "opening", date(2026, 11, 13), "Line ordered", due=date(2026, 9, 25), status="Done"),
                 ChecklistItem("C", "opening", date(2026, 11, 13), "Line installed", due=date(2026, 10, 30), status="Blocked", notes="host comms room"),
                 ChecklistItem("C", "opening", date(2026, 11, 13), "Printers", due=date(2026, 11, 2), status="In progress"),
                 ChecklistItem("F", "opening", date(2026, 11, 26), "Line installed", due=date(2026, 11, 12), status="Done"),
                 ChecklistItem("F", "opening", date(2026, 11, 26), "Staff accounts", due=date(2026, 11, 19), status="Not started"),
                 ChecklistItem("X", "closing", date(2026, 10, 10), "Devices recovered", due=date(2026, 10, 10), status="Not started")]
        devs = [Device("XPC", store="X", role="store PC"), Device("XT", store="X", role="card terminal")]
        f = run_all(data(sts, checklist=items, devices=devs))
        o1 = [x for x in codes(f, "OPN-01") if x.severity != INFO]
        self.assertEqual([(x.severity, x.items) for x in o1], [(CRITICAL, ["C"]), (WARNING, ["C"])])
        self.assertIn("in 10 days), line installed not done (blocked: host comms room)", o1[0].detail)
        self.assertIn("printers overdue since 02 Nov", o1[1].detail)
        self.assertEqual([x.severity for x in codes(f, "OPN-01")], [CRITICAL, WARNING, INFO])
        o2 = codes(f, "OPN-02")[0]
        self.assertEqual((o2.severity, o2.items), (CRITICAL, ["X"]))
        self.assertIn("2 devices not recovered (card terminal 1, store PC 1)", o2.detail)
        self.assertEqual(codes(f, "OPN-03")[0].severity, INFO)

    def test_joiners_leavers_and_shared_accounts(self):
        sts = [store("A"), store("X", closing_date=date(2026, 10, 1))]
        sts[1].status = "closed"
        staff = [Staff("1", "Ana", "A", "Optician", start=TODAY + timedelta(days=1)), Staff("2", "Leo", "A", "Optician", start=TODAY + timedelta(days=1)),
                 Staff("3", "Eva", "A", "Optician", start=TODAY + timedelta(days=6)), Staff("4", "Rui", "A", "Optician", start=TODAY + timedelta(days=20)),
                 Staff("5", "Sol", "A", "Manager", start=date(2020, 1, 1), end=TODAY - timedelta(days=10)),
                 Staff("6", "Noa", "A", "Manager", start=date(2020, 1, 1), end=TODAY - timedelta(days=10))]
        accs = [Account("leo@x", "Leo", "2"), Account("sol@x", "Sol", "5"), Account("noa@x", "Noa", "6", enabled=False),
                Account("store.a@x", "Store A", "", True, "A"), Account("store.x@x", "Store X", "", True, "X")]
        f = run_all(data(sts, staff=staff, accounts=accs, shared_account_match=r"^store\."))
        self.assertEqual([(x.severity, x.items) for x in codes(f, "USR-01")], [(CRITICAL, ["A"]), (WARNING, ["A"])])
        self.assertIn("Ana", codes(f, "USR-01")[0].detail)
        self.assertNotIn("Rui", " ".join(x.detail for x in codes(f, "USR-01")))
        self.assertIn("sol@x still enabled (10 days)", codes(f, "USR-02")[0].detail)
        self.assertEqual(codes(f, "USR-03")[0].items, ["X"])


def load_stores_status(s: Store) -> Store:
    from storehealth.model import store_status
    s.status = store_status(s.status if s.status == "refurbishment" else "", s.opening_date, s.closing_date, TODAY)
    return s


class TestVerdictAndDemo(unittest.TestCase):
    def test_store_rag_visit_list_and_overall(self):
        sts = [store("A", region="Norte", field_tech="Iker"), store("B", region="Norte", field_tech="Iker"), store("C")]
        conn = [x for s in "ABC" for x in days(s)]
        f = run_all(data(sts, conn))
        self.assertEqual((overall(f), set(area_status(f).values())), ("on track", {"ok"}))
        prs = [Printer("B-MFP", "B", "A4", "MFP", toner=0.12, last_seen=AS_OF), Printer("A-RCP", "A", "receipt", "TM", last_seen=AS_OF - timedelta(days=3))]
        d = data(sts, conn, printers=prs, previous={"A": "green", "C": "red"})
        rv = review(d)
        self.assertEqual([(v["store"].id, v["kind"], v["rank"]) for v in rv["visits"]], [("A", "ship", 1), ("B", "ship", 2)])
        self.assertEqual((rv["trend"]["new_red"], rv["trend"]["fixed"]), (["A"], ["C"]))
        f = run_all(d, rv)
        self.assertEqual((overall(f), area_status(f)["Devices"], area_status(f)["Connectivity"]), ("action needed", CRITICAL, "ok"))
        self.assertEqual(summary(d, rv)["red"], 1)
        f = run_all(data(sts, conn, printers=prs[:1]))
        self.assertEqual(overall(f), "attention")

    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS}
                              | {n.name: hashlib.sha1(n.read_bytes()).hexdigest() for n in (Path(t) / f"data{k}").iterdir()})
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(json.loads((Path(t) / "data0" / "settings.json").read_text(encoding="utf-8"))["as_of"], "2026-11-03 08:00")
            d = load(Path(t) / "data0")
            visits = list(csv.DictReader(open(Path(t) / "out0" / "visits.csv", encoding="utf-8")))
        rv = review(d)
        f = run_all(d, rv)
        sm = summary(d, rv)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        self.assertEqual(overall(f), "action needed")
        for c in ("CON-01", "CON-02", "CON-03", "CON-04", "CON-05", "CON-06", "CON-07", "CON-08", "DEV-01", "DEV-02", "DEV-03", "DEV-04", "DEV-05",
                  "DEV-06", "DEV-07", "DEV-08", "DEV-09", "TKT-01", "TKT-02", "TKT-03", "TKT-04", "TKT-05", "OPN-01", "OPN-02", "OPN-03", "USR-01",
                  "USR-02", "USR-03"):
            self.assertIn(c, {x.code for x in f})
        self.assertEqual((d.settings.organisation, sm["stores"], sm["trading"], sm["never_tested"], sm["no_backup"], sm["unsupported"], sm["openings"],
                          sm["closed_pending"]), ("Northwind Optics", 122, 116, 14, 3, 22, 2, 2))
        self.assertIn("9 failovers", codes(f, "CON-02")[0].detail)
        self.assertIn("Levante: the tunnel flaps at 17 of 17 stores", codes(f, "CON-07")[0].detail)
        self.assertIn("(in 10 days), line installed not done", codes(f, "OPN-01")[0].detail)
        self.assertEqual(len(codes(f, "DEV-05")[0].items), 3)
        self.assertEqual([x.severity for x in codes(f, "DEV-09")], [CRITICAL, WARNING])
        self.assertIn("4.5x the estate median", codes(f, "TKT-01")[0].detail)
        self.assertEqual(len(codes(f, "USR-01")[0].items), 2)
        self.assertTrue({"visit", "ship", "vendor"} <= {v["kind"] for v in visits})

    def test_settings_override_sla_and_end_of_servicing(self):
        sts = [store("A")]
        devs = [Device("PC1", "Windows", "10.0.26100.6899", AS_OF, store="A", role="store PC")]
        tks = [tk(1, "A", AS_OF - timedelta(hours=30), pri=3, state="In Progress")]
        f = run_all(data(sts, devices=devs, tickets=tks))
        self.assertFalse(codes(f, "TKT-03") or codes(f, "DEV-02"))
        f = run_all(data(sts, devices=devs, tickets=tks, sla_hours={"3": 24}, os_end_of_servicing={"26100": "2026-11-20"}))
        self.assertIn("SLA 24 h", codes(f, "TKT-03")[0].detail)
        self.assertIn("reaches end of servicing on 20 Nov 2026", codes(f, "DEV-02")[0].detail)

    def test_pack_and_csv_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["demo", "--data", str(Path(t) / "d"), "--out", str(Path(t) / "o")]), 0)
            pack = (Path(t) / "o" / "store-review.md").read_text(encoding="utf-8")
            stores = list(csv.DictReader(open(Path(t) / "o" / "stores.csv", encoding="utf-8")))
            visits = list(csv.DictReader(open(Path(t) / "o" / "visits.csv", encoding="utf-8")))
            html = (Path(t) / "o" / "report.html").read_text(encoding="utf-8")
        for h in ("## 1. Red stores and why", "## 2. Visits and shipments by technician", "## 3. Vendor calls",
                  "## 4. Openings, closings and refurbishments", "## 9. Trend against last week", "## Sign-off"):
            self.assertIn(h, pack)
        self.assertEqual(len(stores), 122)
        self.assertEqual({r["rag"] for r in stores}, {"red", "amber", "green"})
        self.assertTrue(all(r["last_week_rag"] for r in stores))
        techs = {(r["region"], r["field_tech"]) for r in visits}
        self.assertEqual(len({r for r, _ in techs}), len(techs))
        ranks = [int(r["rank"]) for r in visits if r["kind"] != "vendor" and r["field_tech"] == "Álvaro Medina"]
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))
        self.assertIn("Stores by region", html)
        self.assertNotIn("\r", pack)

    def test_review_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            self.assertEqual(cli.main(["review", "--out", str(Path(t) / "o")]), 2)
            write(Path(t) / "stores.csv", ["store_id"], [["NW-1"]])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            write(Path(t) / "tickets.csv", ["number", "opened", "store"], [["INC1", "2026-11-01", "NW-1"]])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o"), "--as-of", "2026-11-03"]), 0)


if __name__ == "__main__":
    unittest.main()
