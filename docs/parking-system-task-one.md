# Modern Parking System — Task One: System Analysis

**Course:** Data Structures and Algorithms
**Scope:** Module identification, algorithms, and data structure justification for an automated parking system (Kenya-based client)

---

## 1. Requirements Analysis

From the client's terms of reference (objectives 1.2 and scope 1.3), the system must:

1. Show live slot availability on a display board and in a web/mobile view.
2. Record each vehicle on arrival — plate number, entry time, and allocated bay.
3. Automatically calculate duration and amount payable on exit.
4. Collect payment (M-Pesa, card, or cash) and open the barrier only on confirmed payment.
5. Let management change parking rates at any time **without a software change**.
6. Produce an auditable record of every shilling collected, for reconciliation and VAT.

These requirements are met by **six modules**. Tracking (Module 1) is the shared core that the other five read from and write to. Requirement 1 (live display board + web/mobile view) is met by Module 2 writing a live status snapshot served over a local web dashboard. Requirement 4 (three distinct payment methods) is met by Module 5 explicitly selecting and recording M-Pesa, card, or cash. Requirement 5 (changeable rates) is met by treating fee tiers as external, editable data rather than hard-coded values (Module 4). Requirement 6 (auditability + reporting) is met by Module 6, which both logs every transaction and generates a collections summary on demand.

| Requirement | Module | Status |
|---|---|---|
| Live display board + web/mobile view | Module 2 | Implemented — interactive local web dashboard; entry/exit/payment/reporting all usable from the browser |
| Record vehicle on arrival | Module 3 | Implemented |
| Auto-calculate duration + fee | Module 4 | Implemented |
| Collect payment (M-Pesa/card/cash), barrier on confirmed payment | Module 5 | Implemented — method explicitly selected and recorded |
| Change rates without a software change | Module 4 | Implemented — external `fee_tiers.json` |
| Auditable record for reconciliation/VAT | Module 6 | Implemented — append-only log |
| Administrative reporting | Module 6 | Implemented — `generateReport()` summary |
| Exception handling | Modules 5 & 2 | Implemented — invalid input re-prompts; display failures degrade gracefully without crashing the core system |

---

## 2. Module 1: Vehicle/Slot Tracking (Core Module)

**Purpose:** Maintains the live state of the parking lot — which slots are occupied, by which vehicle, and since when.

**Data Structures Used:**
- `slotMap` — a **hash map** keyed by slot number, storing `{occupied, plate, arrivalTime}`.
- `plateMap` — a **hash map** keyed by plate number, storing the assigned slot number.

**Justification:** A hash map gives near-instant (O(1)) lookup. `slotMap` answers "is slot X free?" instantly; `plateMap` answers "which slot is this vehicle in?" instantly. Without `plateMap`, finding a vehicle by plate would require scanning every slot (O(n)) — too slow as the lot grows. Using two maps trades a small amount of extra memory for speed on both directions of lookup.

**Algorithm:**
```
FUNCTION isSlotFree(slotNumber):
    RETURN slotMap[slotNumber].occupied == false

FUNCTION occupySlot(slotNumber, plate, arrivalTime):
    slotMap[slotNumber] = {occupied: true, plate: plate, arrivalTime: arrivalTime}
    plateMap[plate] = slotNumber

FUNCTION freeSlot(plate):
    slotNumber = plateMap[plate]
    slotMap[slotNumber] = {occupied: false, plate: null, arrivalTime: null}
    REMOVE plate FROM plateMap
```

---

## 3. Module 2: Slot Display (Availability) + Interactive Web/Mobile Dashboard

**Purpose:** Shows drivers, before entry, how many/which slots are free — and satisfies the client requirement that this be visible both on a display board at the entrance and in a web or mobile view. The dashboard is fully interactive: vehicle entry, exit, payment, and reporting can all be carried out directly from the browser, not only from the console.

**Data Structures Used:** None of its own for the availability calculation — reads directly from `slotMap` (Module 1). The live view is served by a small built-in web server exposing a JSON API (`/api/status`, `/api/entry`, `/api/exit/quote`, `/api/exit/pay`, `/api/report`) that calls the same underlying functions as the console menu, so there is exactly one implementation of each piece of business logic, used by two different front ends.

**Justification:** Not every module needs its own storage; a "view" module can simply read shared state. Scanning all slots is O(n), but this is acceptable since the list of free slots genuinely requires checking every slot at least once, and a real-world lot size (tens to hundreds of slots) makes this scan trivially fast. Having the console and the web dashboard call the *same* functions (rather than each having their own copy of the entry/exit/billing logic) avoids duplicated logic that could drift out of sync — a change to a fee rule or a validation check only has to be made once. Because both interfaces can now trigger changes to shared state at the same time, a lock (`state_lock`) is used around any block that reads or modifies `slotMap`/`plateMap`/the slot queue, so a browser action and a console action can never corrupt each other's changes.

**Algorithm:**
```
FUNCTION getAvailableSlots():
    availableList = empty list
    FOR each slotNumber in slotMap:
        IF slotMap[slotNumber].occupied == false:
            ADD slotNumber TO availableList
    RETURN availableList

FUNCTION getAvailableCount():
    RETURN length of getAvailableSlots()
```

---

## 4. Module 3: Entry / Check-in

**Purpose:** Assigns an arriving vehicle to a free slot and records its arrival time.

**Data Structures Used:** `availableSlotQueue` — a **queue** (FIFO) of free slot numbers.

**Justification:** A queue makes slot assignment an O(1) "remove from front" operation, avoiding a scan for the first free slot. It also gives a fair, predictable round-robin assignment order rather than always filling the lowest-numbered slot.

**Algorithm:**
```
FUNCTION vehicleEntry(plate):
    IF availableSlotQueue is empty:
        DISPLAY "Parking full"
        RETURN failure

    slotNumber = REMOVE FRONT of availableSlotQueue
    arrivalTime = CURRENT_TIME
    occupySlot(slotNumber, plate, arrivalTime)   // Module 1
    DISPLAY "Welcome. Proceed to slot " + slotNumber
    RETURN success
```

**Design note:** The system should check `plateMap` before assigning a slot, to reject a vehicle that is already recorded as parked (prevents duplicate/erroneous entries).

---

## 5. Module 4: Billing

**Purpose:** Calculates duration parked and the corresponding fee at exit.

**Data Structures Used:** `feeTiers` — a **list of records** (lookup table) of `{maxMinutes, fee}` pairs.

**Justification:** Storing the fee schedule as data rather than as a hard-coded if/else chain separates pricing logic from program logic — the client's fee table can change without touching the algorithm itself.

**Fee table (from client brief):**

| Duration | Fee (Kshs) |
|---|---|
| Up to 30 minutes | 0 (free) |
| Up to 2 hours | 50 |
| Up to 4 hours | 100 |
| Up to 6 hours | 300 |
| Over 6 hours | 500 |

**Algorithm:**
```
feeTiers = [
    {maxMinutes: 30,       fee: 0},
    {maxMinutes: 120,      fee: 50},
    {maxMinutes: 240,      fee: 100},
    {maxMinutes: 360,      fee: 300},
    {maxMinutes: INFINITY, fee: 500}
]

FUNCTION calculateFee(plate):
    slotNumber = plateMap[plate]
    arrivalTime = slotMap[slotNumber].arrivalTime
    exitTime = CURRENT_TIME
    durationMinutes = (exitTime - arrivalTime) in minutes

    FOR each tier in feeTiers:
        IF durationMinutes <= tier.maxMinutes:
            RETURN {duration: durationMinutes, amountDue: tier.fee}
```

**Design note:** Tiers are cumulative bands (a flat fee up to a ceiling), not per-hour charges. Checking `durationMinutes <= tier.maxMinutes` against a rising ceiling avoids gaps or overlaps between bands.

**Design note (rate changes without a software change):** The client's terms of reference require that management can change rates at any time without a software change. Storing `feeTiers` as a literal, hard-coded list inside the program does not satisfy this — updating a price would still mean editing and re-deploying code. To meet this properly, `feeTiers` should be **loaded at runtime from an external source** — a configuration file (e.g. JSON) or the `fee_tiers` database table (see Part c). The algorithm above stays identical either way; only *where the data comes from* changes.

---

## 6. Module 5: Exit / Barrier Control

**Purpose:** Coordinates billing, payment confirmation, and barrier release.

**Data Structures Used:** None of its own — calls into Modules 1, 3, and 4.

**Algorithm:**
```
FUNCTION vehicleExit(plate):
    IF plate NOT IN plateMap:
        DISPLAY "Vehicle not recognized"
        RETURN failure

    billResult = calculateFee(plate)              // Module 4

    IF billResult.amountDue == 0:
        paymentConfirmed = true                   // free tier, nothing to collect
        method = "N/A (free)"
    ELSE:
        method = selectPaymentMethod()             // prompts: M-Pesa / Card / Cash
        DISPLAY "Amount due: Kshs " + billResult.amountDue + " via " + method
        paymentConfirmed = processPayment(billResult.amountDue)

    IF paymentConfirmed:
        slotNumber = plateMap[plate]
        logTransaction(plate, slotNumber, ..., billResult.amountDue, method)  // Module 6
        freeSlot(plate)                           // Module 1
        ADD slotNumber TO availableSlotQueue       // Module 3
        openBarrier()
        RETURN success
    ELSE:
        DISPLAY "Payment failed, barrier remains closed"
        RETURN failure
```

**Design note (payment methods):** The terms of reference name three specific channels — M-Pesa, card, and cash. Rather than treating "payment" as one generic step, the exit flow now explicitly asks which method was used and records it on the transaction, satisfying "collect payment by M-Pesa, card or cash" as a real distinction rather than a placeholder. A full production build would additionally call each channel's real API (M-Pesa STK push, a card terminal, etc.); this phase models the selection and recording of the method without wiring up live payment processors.

**Design note (exception handling):** The terms of reference name "exception handling" explicitly in scope. Two failure points are guarded here: an invalid method choice (re-prompts rather than crashing) and non-numeric payment input (re-prompts rather than raising an unhandled error and killing the whole program). This is a general principle worth stating in your report: any point where the program reads free-form input from a human is a point where exception handling is required, since people mistype.

---

## 7. Module 6: Reporting / Audit Trail

**Purpose:** Satisfies the client's requirement to "produce an auditable record of every shilling collected, for reconciliation and VAT." Without this module, a completed transaction's details (amount paid, plate, time) are discarded the moment `freeSlot` runs — nothing survives to be reconciled or audited later.

**Data Structures Used:** An **append-only log** — each completed, paid transaction is written as one record to persistent storage (a log file, or the `parking_sessions` row itself, per Part c) and never edited afterward. Append-only is the key property for auditability: a record that can be silently altered after the fact defeats the purpose of an audit trail.

**Justification:** Reconciliation and VAT reporting require a permanent, unmodifiable history of every payment collected — not just current lot state (which Module 1 already discards on exit). An append-only log is the simplest structure that guarantees history is preserved and tamper-evident (records are only ever added, never overwritten).

**Algorithm:**
```
FUNCTION logTransaction(plate, slotNumber, arrivalTime, exitTime, amountPaid, paymentMethod):
    record = {
        plate: plate,
        slot: slotNumber,
        arrivalTime: arrivalTime,
        exitTime: exitTime,
        amountPaid: amountPaid,
        paymentMethod: paymentMethod,
        loggedAt: CURRENT_TIME
    }
    APPEND record TO auditLog   // never overwrite or delete existing records
```

**Design note:** This is called from Module 5 (`vehicleExit`), immediately after payment is confirmed and before the slot is freed — so every successful transaction is captured, and only successful (paid) transactions appear in the trail.

**Administrative reporting:** The terms of reference also require "administrative reporting" as a distinct capability from the raw audit record. A `generateReport()` function reads the full audit log and produces a summary: total transactions, total Kshs collected, and a breakdown by payment method. This is the human-facing use of the audit trail — the log itself is the source of truth; the report is a derived view over it, so it never needs its own separate storage.
```
FUNCTION generateReport():
    records = READ ALL FROM auditLog
    totalCollected = SUM of record.amountPaid for all records
    countByMethod = GROUP records BY paymentMethod, COUNT each group
    DISPLAY totalCollected, countByMethod
```

---

## 8. Consolidated Data Structures Summary

| Data Structure | Type | Used By | Reason for Choice |
|---|---|---|---|
| `slotMap` | Hash map (slot number → record) | Tracking, Display | O(1) lookup of a slot's occupancy status |
| `plateMap` | Hash map (plate → slot number) | Tracking, Entry, Billing, Exit | O(1) lookup of a vehicle's slot, avoiding a full scan |
| `availableSlotQueue` | Queue (FIFO) | Entry, Exit | O(1) slot assignment; fair round-robin reuse of slots |
| `feeTiers` | List of records (lookup table) | Billing | Separates pricing rules from program logic; easy to update |
| `auditLog` | Append-only log | Reporting/Audit | Permanent, tamper-evident record for reconciliation and VAT |
| `slotStatusSnapshot` | JSON file (serialized record) | Slot Display / Dashboard | Decouples the live web/mobile display from the console program; either can fail independently |

---

## 9. Module Interaction Overview

```
                 ┌─────────────────────────┐
                 │  Vehicle/Slot Tracking   │  (slotMap, plateMap)
                 │        (Module 1)        │
                 └───────────┬─────────────┘
             reads/writes    │    reads/writes
        ┌────────────────────┼────────────────────┐
        │                    │                     │
┌───────▼───────┐   ┌────────▼────────┐   ┌────────▼────────┐
│ Slot Display  │   │  Entry/Check-in │   │     Billing     │
│  (Module 2)   │   │   (Module 3)    │   │   (Module 4)    │
└───────────────┘   └────────┬────────┘   └────────┬────────┘
                              │                     │
                              │   ┌─────────────────┘
                              │   │
                     ┌────────▼───▼────────┐
                     │  Exit/Barrier Ctrl   │
                     │     (Module 5)       │
                     └──────────┬───────────┘
                                │  on confirmed payment
                     ┌──────────▼───────────┐
                     │  Reporting/Audit     │
                     │     (Module 6)       │
                     └──────────────────────┘
```

---

## 10. Part (c): Dynamic Database Design

The in-memory structures in Modules 1–5 (hash maps, queue) exist only while the program runs. A **database** is persistent — it survives shutdowns and allows lookups of past activity (e.g. "how much did plate KDA 123X pay last Tuesday?"). "Dynamic" here means the data changes constantly in real time as vehicles arrive and leave, as opposed to a static reference table that rarely changes.

A relational schema (tables linked by foreign keys) fits this well.

**`slots`** — one row per physical parking slot (fairly static; status updates dynamically)

| Column | Type | Notes |
|---|---|---|
| slot_id | INT (PK) | |
| slot_number | VARCHAR | e.g. "A12" |
| status | ENUM('free','occupied') | updated dynamically |

**`vehicles`** — one row per plate ever seen (grows over time, rarely changes once created)

| Column | Type | Notes |
|---|---|---|
| vehicle_id | INT (PK) | |
| plate_number | VARCHAR (unique) | |

**`parking_sessions`** — one row per visit; the dynamic core, updated constantly

| Column | Type | Notes |
|---|---|---|
| session_id | INT (PK) | |
| vehicle_id | INT (FK → vehicles) | |
| slot_id | INT (FK → slots) | |
| arrival_time | DATETIME | set on entry |
| exit_time | DATETIME, NULLABLE | NULL while still parked; set on exit |
| amount_due | DECIMAL, NULLABLE | calculated on exit |
| payment_status | ENUM('pending','paid') | |

**`fee_tiers`** — the pricing table (static reference data, edited only when the client changes prices)

| Column | Type | Notes |
|---|---|---|
| tier_id | INT (PK) | |
| max_minutes | INT | |
| fee | DECIMAL | |

**Design rationale:**
- `parking_sessions` is where the "dynamic" behavior lives — a row is created on entry (with `exit_time` and `amount_due` left empty) and updated on exit. This mirrors what `slotMap`/`plateMap` did in memory, but persisted to disk.
- Splitting `vehicles` from `parking_sessions` avoids repeating a plate number's data on every visit — a normalization principle (avoid duplicate data).
- `fee_tiers` as a table (not hard-coded) mirrors the reasoning from Module 4: the client can update prices without a code change.
- A slot's live `status` in the `slots` table is a persisted mirror of the in-memory `slotMap`, so state survives a program restart.

**Relationships (ER overview):** `vehicles (1) —— (many) parking_sessions (many) —— (1) slots`. `parking_sessions.vehicle_id` and `parking_sessions.slot_id` are foreign keys, which is what makes this schema relational.
