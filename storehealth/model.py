"""Loading: the store list, the daily connectivity per store from the monitoring tool (primary line, 4G/LTE backup router, site-to-site
tunnel, AnyConnect), the devices (Intune managed devices, Active Directory computers, card terminals and UPS from their portals), the
printers (SNMP status and supplies from the monitoring tool), the store tickets (ServiceNow or Jira export), the opening, closing and
refurbishment checklists, the HR joiners and leavers with their Entra ID accounts, last week's store status and settings.json; with
forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

STORE_ALIASES = {
    "id": ["store_id", "store id", "store", "site id", "tienda", "loja", "code"],
    "name": ["name", "store name", "nombre"],
    "region": ["region", "area", "zona"],
    "city": ["city", "ciudad", "cidade"],
    "country": ["country", "pais"],
    "format": ["format", "store format", "formato", "type"],
    "status": ["status", "estado"],
    "opening_date": ["opening_date", "opening date", "opens", "apertura"],
    "closing_date": ["closing_date", "closing date", "closes", "cierre"],
    "field_tech": ["field_tech", "field tech", "field technician", "technician", "tecnico"],
    "hours": ["opening_hours", "opening hours", "hours", "horario"],
    "backup": ["backup_line", "backup line", "backup", "backup router"],
    "host": ["host", "department store", "host store"],
}
CONN_ALIASES = {
    "date": ["date", "day", "fecha"],
    "store": ["store_id", "store id", "store", "site"],
    "uptime": ["primary_uptime_pct", "primary uptime pct", "primary uptime", "wan uptime", "uptime"],
    "backup_minutes": ["backup_minutes", "minutes on backup", "backup minutes", "time on backup"],
    "failovers": ["failovers", "failover count", "failover events"],
    "backup_test": ["backup_last_test", "backup last test", "last failover test", "backup tested"],
    "data_used": ["data_used_mb", "data used mb", "data used"],
    "data_cap": ["data_cap_mb", "data cap mb", "data cap", "plan cap"],
    "tunnel_up": ["tunnel_up_pct", "tunnel up pct", "vpn up pct", "tunnel uptime", "vpn uptime"],
    "tunnel_drops": ["tunnel_drops", "tunnel drops", "vpn drops", "tunnel down events"],
    "tunnel_hour": ["tunnel_peak_hour", "tunnel peak hour", "drop hour", "vpn peak hour"],
    "anyconnect": ["anyconnect_failures", "anyconnect failures", "vpn client failures"],
}
DEVICE_ALIASES = {
    "name": ["devicename", "device name", "name", "computer name", "dnshostname", "terminal id"],
    "os": ["operatingsystem", "operating system", "os"],
    "os_version": ["osversion", "os version", "operatingsystemversion", "operating system version"],
    "last_sync": ["lastsyncdatetime", "last sync", "lastlogondate", "last logon date", "last seen", "last report"],
    "model": ["model"],
    "manufacturer": ["manufacturer", "oem"],
    "serial": ["serialnumber", "serial number", "serial"],
    "store": ["store_id", "store id", "store", "officelocation", "site"],
    "role": ["role", "device role", "devicecategorydisplayname", "device category", "category"],
    "source": ["source", "origin", "managementagent"],
    "health": ["health", "status", "self test", "selftest"],
    "battery_date": ["battery_date", "battery date", "battery replaced", "battery installed"],
}
PRINTER_ALIASES = {
    "name": ["printer", "name", "printer name", "sysname"],
    "store": ["store_id", "store id", "store", "site"],
    "type": ["type", "printer type", "kind"],
    "model": ["model", "hrdevicedescr"],
    "ip": ["ip", "ip address", "address"],
    "status": ["status", "hrprinterstatus", "state"],
    "error": ["error", "hrprinterdetectederrorstate", "detected error", "alert"],
    "toner": ["toner_pct", "toner pct", "toner", "supplies level", "level pct"],
    "pages": ["page_count", "page count", "prtmarkerlifecount", "pages"],
    "last_seen": ["last_seen", "last seen", "last poll", "last contact"],
}
TICKET_ALIASES = {
    "number": ["number", "issue key", "key", "id", "ticket"],
    "opened": ["opened_at", "opened", "created", "sys_created_on"],
    "closed": ["closed_at", "closed", "resolved_at", "resolved", "resolution date"],
    "store": ["store_id", "store id", "store", "location", "u_store"],
    "category": ["category", "category / subcategory", "issue type", "component"],
    "priority": ["priority", "prioridad"],
    "state": ["state", "status", "estado"],
    "field_visit": ["field_visit", "field visit", "u_field_visit", "dispatched", "on site"],
    "vendor": ["vendor", "u_vendor", "supplier", "proveedor"],
    "vendor_ref": ["vendor_ref", "vendor ref", "vendor ticket", "u_vendor_ref", "external ref"],
    "short_description": ["short_description", "short description", "summary", "title"],
    "ci": ["cmdb_ci", "ci", "configuration item", "asset"],
}
OPENING_ALIASES = {
    "store": ["store_id", "store id", "store"],
    "event": ["event", "type", "change", "evento"],
    "date": ["date", "event date", "go live", "fecha"],
    "item": ["item", "checklist item", "task"],
    "owner": ["owner", "responsible", "responsable"],
    "due": ["due", "due date", "deadline"],
    "status": ["status", "state", "estado"],
    "notes": ["notes", "comment", "comments", "notas"],
}
STAFF_ALIASES = {
    "employee_id": ["employee_id", "employeeid", "employee id", "id"],
    "name": ["name", "display name", "displayname", "employee"],
    "store": ["store_id", "store id", "store", "location"],
    "role": ["role", "job title", "jobtitle", "position"],
    "start": ["start_date", "start date", "employeehiredate", "hire date", "start"],
    "end": ["end_date", "end date", "leave date", "termination date", "end"],
}
USER_ALIASES = {
    "upn": ["userprincipalname", "user principal name", "upn"],
    "name": ["displayname", "display name", "name"],
    "employee_id": ["employeeid", "employee id", "employee_id"],
    "enabled": ["accountenabled", "account enabled", "enabled"],
    "store": ["officelocation", "office location", "store", "store_id"],
    "created": ["createddatetime", "created", "whencreated"],
}
PREV_ALIASES = {"store": ["store_id", "store id", "store"], "rag": ["rag", "status", "rating"]}

YES = {"yes", "y", "true", "1", "si", "sim", "x", "on"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%m/%d/%Y")
# End of servicing of the Windows versions seen in store estates (Enterprise editions, Microsoft lifecycle); settings.json adds or overrides.
OS_END = {"19044": "2024-06-11", "19045": "2025-10-14", "22000": "2024-10-08", "22621": "2025-10-14", "22631": "2026-11-10",
          "26100": "2027-10-12", "26200": "2028-10-10"}
DEFAULT_OWNERS = {"connectivity": "Network team", "devices": "Store IT support", "tickets": "Service desk lead",
                  "openings": "Store openings coordinator", "users": "Identity and access"}
DEFAULT_SLA = {"1": 4, "2": 8, "3": 72, "4": 120}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"n a", "na", "none", "null", "never", "nunca"}:
        return None
    s = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", "", s)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_d(v) -> date | None:
    x = parse_dt(v)
    return x.date() if x else None


def yes(v) -> bool:
    return _norm(v) in YES


def num(v) -> float | None:
    s = str(v or "").strip().replace("%", "").replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def pct_value(v) -> float | None:
    """'99.5', '99,5 %' or '0.995' -> 0.995."""
    x = num(v)
    if x is None:
        return None
    return x / 100 if x > 1 else x


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = fh.readline()
        fh.seek(0)
        delim = max(",;\t", key=header.count)
        reader = csv.DictReader(fh, delimiter=delim)
        return list(reader.fieldnames or []), list(reader)


def _map(fields: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    heads = {_norm(h): h for h in fields}
    cols = {}
    for k, names in aliases.items():
        for n in names + [k.replace("_", " ")]:
            if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                cols[k] = heads[_norm(n)]
                break
    return cols


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    fields, raw = _read(path)
    cols = _map(fields, aliases)
    return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in raw]


def os_build(v) -> str:
    """'10.0.19045.6456' (Intune) or '10.0 (19045)' (Active Directory) -> '19045'; '' when it is not Windows 10/11."""
    nums = re.findall(r"\d+", str(v or ""))
    big = [n for n in nums if len(n) == 5]
    return big[0] if big else ""


def hours_range(v) -> tuple[int, int]:
    """'10:00-22:00' -> (10, 22); default (10, 21)."""
    m = re.findall(r"(\d{1,2})[:.h]?\d{0,2}", str(v or ""))
    return (int(m[0]), int(m[1])) if len(m) >= 2 else (10, 21)


# ---------------------------------------------------------------- records

@dataclass
class Store:
    id: str
    name: str = ""
    region: str = ""
    city: str = ""
    country: str = ""
    format: str = ""
    status: str = ""
    opening_date: date | None = None
    closing_date: date | None = None
    field_tech: str = ""
    hours: tuple = (10, 21)
    backup: str = ""
    host: str = ""

    @property
    def has_backup(self) -> bool:
        return _norm(self.backup) not in {"", "none", "no", "n a", "ninguno", "sin backup"}

    @property
    def trading(self) -> bool:
        return self.status in ("open", "closing")


@dataclass
class ConnDay:
    day: date
    store: str
    uptime: float | None = None
    backup_minutes: float = 0
    failovers: int = 0
    backup_test: date | None = None
    data_used: float | None = None
    data_cap: float | None = None
    tunnel_up: float | None = None
    tunnel_drops: int = 0
    tunnel_hour: int | None = None
    anyconnect: int = 0


@dataclass
class Device:
    name: str
    os: str = ""
    os_version: str = ""
    last_sync: datetime | None = None
    model: str = ""
    manufacturer: str = ""
    serial: str = ""
    store: str = ""
    role: str = ""
    source: str = ""
    health: str = ""
    battery_date: date | None = None

    @property
    def kind(self) -> str:
        n = _norm(self.role)
        for k, words in (("ups", ("ups", "sai")), ("terminal", ("terminal", "pin pad", "pinpad", "payment", "tpv")),
                         ("handheld", ("handheld", "tablet", "scanner", "pda")), ("laptop", ("laptop", "portatil", "notebook")),
                         ("backoffice", ("back office", "backoffice")), ("pc", ("pc", "desktop", "counter", "workstation"))):
            if any(w in n for w in words):
                return k
        return "other"


@dataclass
class Printer:
    name: str
    store: str = ""
    type: str = ""
    model: str = ""
    ip: str = ""
    status: str = ""
    error: str = ""
    toner: float | None = None
    pages: int | None = None
    last_seen: datetime | None = None

    @property
    def kind(self) -> str:
        n = _norm(self.type + " " + self.model)
        return "receipt" if "receipt" in n or "ticket" in n or "tm t" in n else "label" if "label" in n or "etiqueta" in n else "a4"


@dataclass
class Ticket:
    number: str
    opened: datetime | None = None
    closed: datetime | None = None
    store: str = ""
    category: str = ""
    priority: int = 4
    state: str = ""
    field_visit: bool = False
    vendor: str = ""
    vendor_ref: str = ""
    short_description: str = ""
    ci: str = ""

    @property
    def is_open(self) -> bool:
        s = _norm(self.state)
        return not self.closed and not any(w in s for w in ("closed", "resolved", "cancel", "done", "cerrad", "resuelt"))

    @property
    def group(self) -> str:
        return re.split(r"\s*[/>|]\s*", self.category)[0].strip() or "Other"


@dataclass
class ChecklistItem:
    store: str
    event: str
    date: date | None
    item: str
    owner: str = ""
    due: date | None = None
    status: str = ""
    notes: str = ""

    @property
    def done(self) -> bool:
        s = _norm(self.status)
        return s in {"done", "complete", "completed", "yes", "ok", "hecho", "n a", "na"}

    @property
    def blocked(self) -> bool:
        return "block" in _norm(self.status) or "bloque" in _norm(self.status)


@dataclass
class Staff:
    employee_id: str
    name: str = ""
    store: str = ""
    role: str = ""
    start: date | None = None
    end: date | None = None


@dataclass
class Account:
    upn: str
    name: str = ""
    employee_id: str = ""
    enabled: bool = True
    store: str = ""
    created: datetime | None = None


@dataclass
class Settings:
    organisation: str = "Store IT health review"
    as_of: datetime | None = None
    week_days: int = 7
    ticket_days: int = 30
    uptime_warning: float = 0.99
    uptime_critical: float = 0.95
    failover_warning: int = 3
    failover_critical: int = 6
    backup_minutes_warning: int = 240
    backup_minutes_critical: int = 1440
    backup_test_max_days: int = 90
    data_cap_warning: float = 0.8
    data_cap_critical: float = 0.9
    tunnel_up_min: float = 0.995
    tunnel_flap_days: int = 4
    region_flap_share: float = 0.5
    anyconnect_warning: int = 5
    stale_days: int = 7
    stale_visit_days: int = 21
    terminal_stale_hours: int = 24
    handheld_stale_days: int = 3
    printer_offline_hours: int = 12
    printer_ship_hours: int = 48
    toner_warning: float = 0.15
    toner_critical: float = 0.05
    ups_battery_years: float = 4
    jam_repeat: int = 3
    jam_model_stores: int = 3
    ticket_ratio_warning: float = 3
    ticket_ratio_critical: float = 4
    ticket_min: int = 8
    repeat_count: int = 3
    vendor_open_days: int = 3
    sla_hours: dict = field(default_factory=lambda: dict(DEFAULT_SLA))
    opening_weeks: int = 4
    opening_critical_days: int = 14
    joiner_days: int = 7
    leaver_grace_days: int = 1
    shared_account_match: str = r"^(store|tienda|loja)[._-]"
    os_end_of_servicing: dict = field(default_factory=dict)
    supported_android_min: int = 11
    owners: dict = field(default_factory=lambda: dict(DEFAULT_OWNERS))

    def owner(self, area: str) -> str:
        return self.owners.get(area) or DEFAULT_OWNERS.get(area, "IT")

    def os_end(self, build: str) -> date | None:
        v = self.os_end_of_servicing.get(build) or OS_END.get(build)
        return parse_d(v) if v else None


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k) or v is None:
            continue
        cur = getattr(s, k)
        if k == "as_of":
            s.as_of = parse_dt(v)
        elif isinstance(cur, dict):
            cur.update({str(a): b for a, b in v.items()})
        elif isinstance(cur, bool):
            setattr(s, k, bool(v))
        elif isinstance(cur, int):
            setattr(s, k, int(num(v) or 0))
        elif isinstance(cur, float):
            setattr(s, k, float(num(v) or 0))
        else:
            setattr(s, k, v)
    return s


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    stores: list[Store] = field(default_factory=list)
    conn: list[ConnDay] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    printers: list[Printer] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    checklist: list[ChecklistItem] = field(default_factory=list)
    staff: list[Staff] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    previous: dict = field(default_factory=dict)        # store id -> RAG of last week's review
    sources: dict = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def store(self, sid: str) -> Store | None:
        return self.by_id.get(sid)

    @property
    def by_id(self) -> dict:
        return {s.id: s for s in self.stores}


# ---------------------------------------------------------------- loaders

def _int(v, default=0):
    x = num(v)
    return default if x is None else int(x)


def store_status(explicit: str, opening: date | None, closing: date | None, today: date) -> str:
    n = _norm(explicit)
    if "refurb" in n or "reform" in n or "renov" in n:
        return "refurbishment"
    if closing and closing <= today:
        return "closed"
    if "closed" in n or "cerrad" in n:
        return "closed"
    if opening and opening > today:
        return "opening"
    if closing:
        return "closing"
    return "open"


def load_stores(path: Path, today: date) -> list[Store]:
    out = []
    for r in _rows(path, STORE_ALIASES):
        if not r.get("id"):
            continue
        op, cl = parse_d(r.get("opening_date")), parse_d(r.get("closing_date"))
        out.append(Store(r["id"], r.get("name", "") or r["id"], r.get("region", "") or "(no region)", r.get("city", ""), r.get("country", ""),
                         r.get("format", ""), store_status(r.get("status", ""), op, cl, today), op, cl, r.get("field_tech", ""),
                         hours_range(r.get("hours")), r.get("backup", ""), r.get("host", "")))
    return out


def load_conn(path: Path) -> list[ConnDay]:
    out = []
    for r in _rows(path, CONN_ALIASES):
        d = parse_d(r.get("date"))
        if not d or not r.get("store"):
            continue
        h = num(r.get("tunnel_hour"))
        out.append(ConnDay(d, r["store"], pct_value(r.get("uptime")), num(r.get("backup_minutes")) or 0, _int(r.get("failovers")),
                           parse_d(r.get("backup_test")), num(r.get("data_used")), num(r.get("data_cap")), pct_value(r.get("tunnel_up")),
                           _int(r.get("tunnel_drops")), int(h) if h is not None else None, _int(r.get("anyconnect"))))
    return out


def load_devices(path: Path) -> list[Device]:
    return [Device(r["name"], r.get("os", ""), r.get("os_version", ""), parse_dt(r.get("last_sync")), r.get("model", ""), r.get("manufacturer", ""),
                   r.get("serial", ""), r.get("store", ""), r.get("role", ""), r.get("source", ""), r.get("health", ""), parse_d(r.get("battery_date")))
            for r in _rows(path, DEVICE_ALIASES) if r.get("name")]


def load_printers(path: Path) -> list[Printer]:
    out = []
    for r in _rows(path, PRINTER_ALIASES):
        if not r.get("name"):
            continue
        t = num(r.get("toner"))
        out.append(Printer(r["name"], r.get("store", ""), r.get("type", ""), r.get("model", ""), r.get("ip", ""), r.get("status", ""),
                           r.get("error", ""), None if t is None or t < 0 else (t / 100 if t > 1 else t), _int(r.get("pages"), None),
                           parse_dt(r.get("last_seen"))))
    return out


def load_tickets(path: Path) -> list[Ticket]:
    out = []
    for r in _rows(path, TICKET_ALIASES):
        if not r.get("number"):
            continue
        m = re.search(r"\d", r.get("priority", ""))
        out.append(Ticket(r["number"], parse_dt(r.get("opened")), parse_dt(r.get("closed")), r.get("store", ""), r.get("category", ""),
                          int(m.group()) if m else 4, r.get("state", ""), yes(r.get("field_visit")), r.get("vendor", ""), r.get("vendor_ref", ""),
                          r.get("short_description", ""), r.get("ci", "")))
    return out


def load_checklist(path: Path) -> list[ChecklistItem]:
    return [ChecklistItem(r["store"], _norm(r.get("event")) or "opening", parse_d(r.get("date")), r.get("item", ""), r.get("owner", ""),
                          parse_d(r.get("due")), r.get("status", ""), r.get("notes", ""))
            for r in _rows(path, OPENING_ALIASES) if r.get("store")]


def load_staff(path: Path) -> list[Staff]:
    return [Staff(r.get("employee_id", ""), r.get("name", ""), r.get("store", ""), r.get("role", ""), parse_d(r.get("start")), parse_d(r.get("end")))
            for r in _rows(path, STAFF_ALIASES) if r.get("employee_id") or r.get("name")]


def load_accounts(path: Path) -> list[Account]:
    return [Account(r["upn"], r.get("name", ""), r.get("employee_id", ""), r.get("enabled", "true") == "" or yes(r.get("enabled", "true")),
                    r.get("store", ""), parse_dt(r.get("created")))
            for r in _rows(path, USER_ALIASES) if r.get("upn")]


def load_previous(path: Path) -> dict:
    return {r["store"]: r.get("rag", "").lower() for r in _rows(path, PREV_ALIASES) if r.get("store")}


FILES = {
    "stores.csv": "Store list: region, format, status, dates, field technician, hours, backup line",
    "connectivity.csv": "Daily per store from the monitoring tool: primary line, 4G/LTE backup, site-to-site tunnel, AnyConnect",
    "devices.csv": "Intune managed devices, Active Directory computers, card terminals and UPS",
    "printers.csv": "Printer status and supplies (SNMP Printer-MIB via the monitoring tool)",
    "tickets.csv": "Store tickets of the last weeks (ServiceNow or Jira export)",
    "openings.csv": "Opening, closing and refurbishment checklists",
    "staff.csv": "HR joiners and leavers of the stores",
    "users.csv": "Entra ID accounts of store staff and shared store accounts",
    "previous-stores.csv": "Last week's stores.csv output, for the trend",
}


def _find(folder: Path, name: str) -> Path | None:
    p = folder / name
    if p.exists():
        return p
    alts = sorted(x for x in folder.glob(f"{name.rsplit('.', 1)[0]}*.csv") if not (name == "stores.csv" and x.name.startswith("stores-prev")))
    return alts[0] if alts else None


def load(folder: Path, as_of: datetime | None = None) -> Data:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"no folder {folder}")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    paths = {n: _find(folder, n) for n in FILES}
    if not paths["stores.csv"]:
        raise FileNotFoundError(f"{folder}: need stores.csv ({FILES['stores.csv']})")
    if not any(paths[n] for n in ("connectivity.csv", "devices.csv", "printers.csv", "tickets.csv", "openings.csv")):
        raise FileNotFoundError(f"{folder}: need at least one of connectivity.csv, devices.csv, printers.csv, tickets.csv, openings.csv")
    d = Data(s, when)
    d.stores = load_stores(paths["stores.csv"], when.date())
    loaders = {"connectivity.csv": ("conn", load_conn), "devices.csv": ("devices", load_devices), "printers.csv": ("printers", load_printers),
               "tickets.csv": ("tickets", load_tickets), "openings.csv": ("checklist", load_checklist), "staff.csv": ("staff", load_staff),
               "users.csv": ("accounts", load_accounts), "previous-stores.csv": ("previous", load_previous)}
    for n, (attr, fn) in loaders.items():
        if paths[n]:
            setattr(d, attr, fn(paths[n]))
    d.sources = {"stores.csv": len(d.stores)}
    d.sources.update({n: len(getattr(d, attr)) for n, (attr, _) in loaders.items() if paths[n]})
    return d


__all__ = ["Data", "Settings", "Store", "ConnDay", "Device", "Printer", "Ticket", "ChecklistItem", "Staff", "Account", "load", "os_build"]
