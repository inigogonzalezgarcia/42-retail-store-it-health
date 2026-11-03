# Data format

Put the files in one folder and run `python -m storehealth review <folder>`. `stores.csv` is required, plus at least one of `connectivity.csv`, `devices.csv`, `printers.csv`, `tickets.csv` and `openings.csv`; each file adds its checks. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the alternatives below are accepted. Dates as ISO 8601 (`2026-11-01T22:10:05Z`), `yyyy-MM-dd HH:mm`, `dd/mm/yyyy` or `MM/dd/yyyy HH:mm` (day first wins when both read as a date); the time zone suffix is ignored. Percentages as `99.5`, `99,5 %` or `0.995`.

`scripts/Export-StoreHealthData.ps1` writes `devices.csv` from Microsoft Graph (and Active Directory with `-ADSearchBase`) and `users.csv` from Entra ID. The other files come from the tools that hold the data: your store list, the network monitoring tool, the ITSM tool, the openings tracker and HR.

## How the review works

| Step | Rule |
|---|---|
| Store status | `status` when it says refurbishment or closed; otherwise from the dates: closed when `closing_date` is today or earlier, opening when `opening_date` is in the future, closing when it has a future `closing_date`, open otherwise. Only open and closing stores are **trading** |
| Week | The last `week_days` full days before the reference date; the week before gives the trend |
| Store status (RAG) | Red with a critical issue, amber with a warning, green otherwise. Refurbishment stores are not checked until they reopen; closed stores only for devices and accounts; opening stores for their checklist |
| Kind of action | Every issue is a visit (field technician), ship (courier to the store), vendor call or remote work. visits.csv groups the first three by region and technician |
| Tickets | Opened in the last `ticket_days`; the estate median is over trading stores. Tickets whose state contains *hold*, *awaiting* or *pending vendor* do not count against the SLA |

## stores.csv

| Column | Also accepted | Notes |
|---|---|---|
| store_id | store, site id | Joins every other file |
| name, region, city, country | | The grid in the report is by region |
| format | store format | street, shopping centre, department store corner… shown with every issue |
| status | | `refurbishment` or `closed`; empty to derive it from the dates |
| opening_date, closing_date | | A future opening date makes it an opening store; a closing date a closing or closed store |
| field_tech | field technician | The visit and ship list is grouped by it |
| opening_hours | hours | `10:00-22:00`; tunnel drops inside these hours make the regional pattern critical (CON-07) |
| backup_line | backup | `4G/LTE router`, or `none` (CON-05) |
| host | department store | For corners inside a department store |

## connectivity.csv

One row per store and day from the network monitoring tool (the routers' export, or the carrier's portal), at least the last two weeks.

| Column | Also accepted | Notes |
|---|---|---|
| date, store_id | | |
| primary_uptime_pct | wan uptime | Primary line availability that day. Weekly average under `uptime_warning` / `uptime_critical` (CON-01); under 5% on the last day is "line down", with the number of days |
| backup_minutes, failovers | minutes on backup, failover count | Weekly totals against `failover_warning` / `failover_critical` and `backup_minutes_warning` / `backup_minutes_critical` (CON-02) |
| backup_last_test | last failover test | Date of the last failover test of the backup router, on the latest day; empty is never (CON-03, `backup_test_max_days`) |
| data_used_mb, data_cap_mb | | Backup SIM usage in the current billing cycle, on the latest day (CON-04, `data_cap_warning` / `data_cap_critical`) |
| tunnel_up_pct, tunnel_drops, tunnel_peak_hour | vpn up pct, vpn drops | Site-to-site tunnel to head office. A store flaps with drops on `tunnel_flap_days` days of the week or under `tunnel_up_min` (CON-06); a region flaps when `region_flap_share` of its stores do (CON-07) |
| anyconnect_failures | | Failed Cisco AnyConnect connections from the store's laptops (CON-08, `anyconnect_warning` in the week) |

## devices.csv

Intune managed devices (`GET /deviceManagement/managedDevices`), domain-joined computers from Active Directory, and the card terminals and UPS from their own portals, one row per device.

| Column | Also accepted | Notes |
|---|---|---|
| deviceName | name, computer name, terminal id | |
| operatingSystem, osVersion | operating system version | `10.0.19045.6456` (Intune) or `10.0 (19045)` (AD). The build gives the end of servicing (Enterprise): 19045 and 22621 14 Oct 2025, 22000 8 Oct 2024, 22631 10 Nov 2026, 26100 12 Oct 2027, 26200 10 Oct 2028; `os_end_of_servicing` overrides (DEV-02) |
| lastSyncDateTime | lastLogonDate, last seen, last report | Computers after `stale_days` (DEV-01, a visit after `stale_visit_days`); card terminals after `terminal_stale_hours` (DEV-07); handhelds after `handheld_stale_days` (DEV-08) |
| model, manufacturer, serialNumber | | Shown |
| store_id | officeLocation, store | Devices of a closed store count as not recovered (OPN-02) |
| role | deviceCategoryDisplayName | store PC, back-office PC, back-office laptop, stock handheld or tablet, card terminal, UPS |
| source | | Intune, Active Directory, Payment provider portal, UPS network card |
| health | status, self test | UPS: a value with *fail* is critical (DEV-09) |
| battery_date | | UPS battery installed; older than `ups_battery_years` is a warning |

## printers.csv

The printer status and supplies your monitoring tool polls over SNMP. The standard objects are `hrPrinterStatus` (1.3.6.1.2.1.25.3.5.1.1) and `hrPrinterDetectedErrorState` (1.3.6.1.2.1.25.3.5.1.2) of the Host Resources MIB (RFC 2790), and `prtMarkerSuppliesLevel` (1.3.6.1.2.1.43.11.1.1.9) over `prtMarkerSuppliesMaxCapacity` (1.3.6.1.2.1.43.11.1.1.8) of the Printer MIB (RFC 3805) for the toner share; negative levels (-2 unknown, -3 some remaining) are read as unknown.

| Column | Also accepted | Notes |
|---|---|---|
| printer, store_id | name | |
| type | | receipt, label, A4 multifunction. A receipt printer offline is critical (DEV-03) |
| model, ip | | Receipt printer jams are grouped by model (DEV-06) |
| status, error | hrPrinterStatus, hrPrinterDetectedErrorState | `offline` counts as offline |
| toner_pct | supplies level | Under `toner_warning` / `toner_critical` (DEV-04) |
| page_count | prtMarkerLifeCount | Shown |
| last_seen | last poll | Offline after `printer_offline_hours`; ship a swap after `printer_ship_hours` |

## tickets.csv

ServiceNow list export of incidents (or a Jira CSV export) for the stores, at least the last `ticket_days` plus anything still open.

| Column | Also accepted | Notes |
|---|---|---|
| number | issue key | |
| opened_at, closed_at | created, resolved | |
| store_id | location, u_store | |
| category | | `Group / Subcategory`; the same category `repeat_count` times is a repeat (TKT-02); *jam* tickets feed DEV-05 |
| priority | | `1 - Critical`…`4 - Low`; SLA hours by priority in `sla_hours` (TKT-03) |
| state | status | Closed, Resolved, Cancelled are closed; On Hold or Awaiting pause the SLA |
| field_visit | u_field_visit | Open with a visit: TKT-04 |
| vendor, vendor_ref | u_vendor, u_vendor_ref | Open with a vendor for more than `vendor_open_days` (TKT-05); critical when it is the telco and the store's line is down or failing over |
| short_description, cmdb_ci | | The CI ties jam tickets to the receipt printer |

Volume: tickets in the window against the estate median, warning from `ticket_ratio_warning` times and critical from `ticket_ratio_critical`, with at least `ticket_min` tickets (TKT-01).

## openings.csv

One row per checklist item of an opening, closing or refurbishment.

| Column | Notes |
|---|---|
| store_id, event, date | event: opening, closing or refurbishment |
| item, owner, due, status, notes | status Done / In progress / Not started / Blocked. An opening within `opening_critical_days` whose *line installed* item is not done is critical; overdue or blocked items are a warning (critical in the last week) |

Closing items whose name contains *recover* or *collect* tell whether the devices were recovered (OPN-02).

## staff.csv and users.csv

`staff.csv` is the HR list of joiners and leavers (employee_id, name, store_id, role, start_date, end_date); `users.csv` is the Entra ID export (userPrincipalName, displayName, employeeId, accountEnabled, officeLocation, createdDateTime). They are joined on the employee id. Joiners starting within `joiner_days` without an enabled account (USR-01, critical when they start tomorrow), leavers past `leaver_grace_days` still enabled (USR-02), and shared accounts (`shared_account_match`, no employee id) of closed or unknown stores still enabled (USR-03).

## previous-stores.csv

Optional: last week's `stores.csv` output (store_id and rag), for the new red stores and those back from red.

## settings.json

Every threshold above, `as_of` (the reference date; without it, now), `organisation` and `owners` (one per area: connectivity, devices, tickets, openings, users).
