# Store health runbook

A weekly review of every store's IT by central IT, for stores with no IT staff on site, ready for the **retail operations meeting** (Tuesday morning works: the weekend's trading is in the data and the week's visits can still be planned). The tool only reads exports; tickets, shipments, visits and account changes are made in the usual tools.

## The weekly cycle

| When | What | From the outputs |
|---|---|---|
| Monday evening | Export devices and accounts (`Export-StoreHealthData.ps1`), the connectivity and printer exports from the monitoring tool, tickets from the ITSM tool; update openings.csv from the openings tracker and staff.csv from HR | – |
| Tuesday 08:00 | Run the review; copy last week's `output/stores.csv` to `data/previous-stores.csv` first | `store-review.md`, `report.html` |
| Tuesday 09:00 | Central IT triage: open the vendor calls, book the shipments, send each technician their list | `visits.csv` filtered by technician |
| Tuesday 10:00 | Retail operations meeting (below) | The pack |
| During the week | Technicians close their visits; the service desk chases vendors | tickets |

## Export and review

1. Export (read-only):
   ```powershell
   .\scripts\Export-StoreHealthData.ps1 -OutputFolder .\data -IncludeUsers -UserLike '*@yourdomain'
   ```
   Add `-ADSearchBase 'OU=Stores,...'` when back-office PCs are domain-joined and not (all) in Intune.
2. Add `stores.csv`, `connectivity.csv`, `printers.csv`, `tickets.csv`, `openings.csv` and `staff.csv`, and check `settings.json` (`as_of`, thresholds, owners).
3. Build the outputs:
   ```bash
   python -m storehealth review data/ --title "Store IT health · week 45"
   ```

## Retail operations meeting (30 minutes)

| Minutes | Topic | From the pack | Who |
|---|---|---|---|
| 5 | Red stores: can each one sell tomorrow? | Headlines, 1 | Central IT lead, retail operations |
| 10 | Visits and shipments by technician, and what the store has to do (receive a box, keep a device switched on) | 2 | Field technicians, area managers |
| 5 | Vendor calls: telco, printer vendor, payment provider; who escalates | 3 | Network team, service desk lead |
| 5 | Openings in the next four weeks, closings and refurbishments | 4 | Store openings coordinator |
| 5 | Joiners and leavers, trend against last week | 8, 9 | Identity and access, central IT lead |

Record the decisions in the pack and keep each week's folder (exports, pack, CSVs).

## How to read it

- **A store on its backup is one failure away from not selling.** A failover that works is good news only once; a store that fails over nine times in a week, or has been on 4G for three days, needs the telco now, and its SIM will reach its data cap before the line is fixed.
- **An untested backup is a hope.** Test every backup router out of trading hours at least once a quarter and record the date; the day the line fails is the wrong day to find the SIM was never activated.
- **A whole region going wrong at the same time is one cause.** When every tunnel of a region drops around 20:00, look at the head-office concentrator, the region's ISP or a scheduled job, not at seventeen stores.
- **The line of a corner depends on the host.** In a department store the carrier reaches the building, but the last metres go through the host's comms room on that floor; book the joint visit early and have a 4G router ready for opening day.
- **One model, one fix.** Receipt printers of the same model jamming in three stores is a vendor call, not three printers to swap one by one.
- **Many tickets from one store usually means one problem.** A store with four times the median, most of them the same category, needs one visit to fix the cause.
- **A closed store still has devices.** Laptops, terminals and handhelds left in a closed store are assets and data: collect them, wipe or retire them and close the line and the accounts.
- **A new starter without an account loses their first day.** Accounts for tomorrow's joiners are this morning's job; the access review covers leavers in depth.
