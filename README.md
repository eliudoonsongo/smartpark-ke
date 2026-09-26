# SmartPark KE

An automated parking management system built for a Data Structures and Algorithms course assignment.

## What it does

- Tracks live slot availability
- **Interactive web/mobile dashboard** (`dashboard.html`) — park vehicles, process exits, select a payment method, and view a collections report, all from the browser
- Also usable entirely from a console menu — both interfaces operate on the same shared state
- Automatically calculates duration and fee on exit
- Collects payment via **M-Pesa, Card, or Cash**, opening the barrier only once payment is confirmed
- Loads parking rates from an external file (`fee_tiers.json`) so they can be changed without editing code
- Logs every completed, paid transaction to `audit_log.csv` (append-only, for reconciliation/VAT)
- Generates a collections report (total revenue + breakdown by payment method) — available both in the console and on the dashboard
- Handles invalid input (bad numbers, invalid menu choices, unrecognized plates) without crashing

## Project structure

```
smartpark-ke/
├── smartpark_ke.py       # all 6 modules, the web API, and the console menu
├── dashboard.html          # interactive web/mobile dashboard
├── fee_tiers.json          # parking rates — edit this to change pricing, no code changes needed
├── audit_log.csv            # auto-generated on first completed payment; permanent transaction log
├── docs/
│   └── parking-system-task-one.md   # Task One: modules, algorithms, data structures, database design
└── README.md
```

## Requirements

- Python 3.8 or later (no external packages needed — everything used is part of the Python standard library)

## Running it

From the project folder, in a terminal:

```bash
python smartpark_ke.py
```

This starts the console menu **and** the web dashboard together, and tries to open your browser automatically to:
```
http://localhost:8000/dashboard.html
```
If it doesn't open automatically, paste that URL into any browser manually while the program is running.

**Using the dashboard:** park a vehicle, look up an exit fee, choose a payment method, confirm payment, and pull up the collections report — all with the on-page forms. The slot grid updates automatically every 2 seconds.

**Using the console instead (or at the same time):**
```
--- SmartPark KE (console) ---
Available slots: 20
1. View available slots
2. Vehicle entry
3. Vehicle exit
4. Generate collections report
5. Quit
6. [TESTING ONLY] Simulate earlier arrival, to test paid exits
```

Both interfaces share the same live data — parking a car via the dashboard will show up if you check available slots in the console, and vice versa.

## Testing the payment flow without waiting hours

Fee tiers only kick in as real time passes (e.g. the "up to 2 hours" tier). Console option 6 (or the "Testing Only" panel on the dashboard) lets you back-date a parked vehicle's arrival time so you can see each tier and the payment flow without waiting. This is clearly marked as a testing convenience, not a client requirement.

## Changing parking rates

Edit `fee_tiers.json` directly — no code change required. `max_minutes: null` marks the open-ended top tier (no ceiling).

## Notes

- `audit_log.csv` is created the first time a payment completes. It's append-only — rows are only ever added, never edited.
- Lot size is set in `main()` inside `smartpark_ke.py` (`initialize_slots(20)`) — change the number there if your assignment specifies a different lot size.
- If port 8000 is already in use on your machine, the console menu still works fine; you'll just see a warning that the web dashboard couldn't start.
