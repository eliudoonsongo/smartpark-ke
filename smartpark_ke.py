"""
SmartPark KE - Automated Parking System
Data Structures and Algorithms - Task Two

Modules:
1. Vehicle/Slot Tracking (core)
2. Slot Display (Availability) + interactive web/mobile dashboard
3. Entry / Check-in
4. Billing
5. Exit / Barrier Control (incl. payment method selection)
6. Reporting / Audit Trail

Both the console menu and the web dashboard call the same underlying
functions, so entry/exit/billing/reporting logic exists in exactly one
place. A lock protects shared state since the console (main thread) and
the web dashboard (server thread) can both trigger changes at the same time.
"""

import csv
import json
import http.server
import socketserver
import threading
import webbrowser
from collections import deque
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# MODULE 1: Vehicle/Slot Tracking (core)
# ---------------------------------------------------------------------------
slot_map = {}
plate_map = {}
available_slot_queue = deque()

# Protects slot_map / plate_map / available_slot_queue from being modified
# by the console and the web dashboard at the same instant.
state_lock = threading.Lock()


def initialize_slots(number_of_slots):
    """Set up the parking lot with the given number of empty slots."""
    for slot_number in range(1, number_of_slots + 1):
        slot_map[slot_number] = {
            "occupied": False,
            "plate": None,
            "arrival_time": None
        }
        available_slot_queue.append(slot_number)


def is_slot_free(slot_number):
    return slot_map[slot_number]["occupied"] == False


def occupy_slot(slot_number, plate, arrival_time):
    slot_map[slot_number] = {
        "occupied": True,
        "plate": plate,
        "arrival_time": arrival_time
    }
    plate_map[plate] = slot_number


def free_slot(plate):
    slot_number = plate_map[plate]
    slot_map[slot_number] = {
        "occupied": False,
        "plate": None,
        "arrival_time": None
    }
    del plate_map[plate]


# ---------------------------------------------------------------------------
# MODULE 2: Slot Display (Availability) + interactive web/mobile dashboard
# ---------------------------------------------------------------------------
# Client requirement: "Show live slot availability on a display board at the
# entrance and in a web or mobile view." The dashboard (dashboard.html) is
# now fully interactive: entry, exit, payment, and reporting can all be done
# from the browser, backed by the small JSON API implemented further down
# in SmartParkRequestHandler. The same page can still be left open on a
# screen at the entrance purely as a display board if no one needs to
# interact with it there.
DASHBOARD_PORT = 8000


def get_available_slots():
    available_list = []
    for slot_number in slot_map:
        if slot_map[slot_number]["occupied"] == False:
            available_list.append(slot_number)
    return available_list


def get_available_count():
    return len(get_available_slots())


def build_status_snapshot():
    """Returns the current slot state as a plain dictionary (JSON-ready)."""
    slots_list = []
    for slot_number in sorted(slot_map.keys()):
        slots_list.append({
            "slot_number": slot_number,
            "occupied": slot_map[slot_number]["occupied"]
        })

    return {
        "generated_at": str(datetime.now()),
        "total_slots": len(slot_map),
        "available_count": get_available_count(),
        "slots": slots_list
    }


def start_dashboard_server():
    """
    Starts the web server (serves dashboard.html and the JSON API) in a
    background thread, so the console menu keeps working normally at the
    same time.
    """
    try:
        httpd = socketserver.ThreadingTCPServer(("", DASHBOARD_PORT), SmartParkRequestHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        dashboard_url = f"http://localhost:{DASHBOARD_PORT}/dashboard.html"
        print(f"Interactive dashboard available at: {dashboard_url}")

        try:
            webbrowser.open(dashboard_url)
        except Exception:
            pass  # not every environment can open a browser; the URL above still works

    except OSError as error:
        # If the port is busy or blocked, the console menu still works --
        # only the web dashboard is unavailable.
        print(f"Warning: could not start the web dashboard ({error})")
        print("The console menu will continue to work normally.")


# ---------------------------------------------------------------------------
# MODULE 3: Entry / Check-in
# ---------------------------------------------------------------------------
def vehicle_entry(plate):
    with state_lock:
        if plate in plate_map:
            return {"success": False, "message": "Vehicle already parked"}

        if len(available_slot_queue) == 0:
            return {"success": False, "message": "Parking full"}

        slot_number = available_slot_queue.popleft()
        arrival_time = datetime.now()
        occupy_slot(slot_number, plate, arrival_time)

    return {"success": True, "message": f"Welcome. Proceed to slot {slot_number}", "slot_number": slot_number}


# ---------------------------------------------------------------------------
# MODULE 4: Billing
# ---------------------------------------------------------------------------
# Fee tiers are loaded from fee_tiers.json rather than hard-coded here, so
# management can change rates by editing that file -- no code change needed
# (client requirement: "let management change parking rates at any time
# without a software change").
FEE_TIERS_FILE = "fee_tiers.json"


def load_fee_tiers():
    with open(FEE_TIERS_FILE, "r") as file:
        tiers = json.load(file)

    # JSON has no representation for infinity, so the file stores the
    # top-tier ceiling as null; convert that back into float("inf") here.
    for tier in tiers:
        if tier["max_minutes"] is None:
            tier["max_minutes"] = float("inf")

    return tiers


fee_tiers = load_fee_tiers()


def calculate_fee(plate):
    slot_number = plate_map[plate]
    arrival_time = slot_map[slot_number]["arrival_time"]
    exit_time = datetime.now()

    duration = exit_time - arrival_time
    duration_minutes = duration.total_seconds() / 60

    for tier in fee_tiers:
        if duration_minutes <= tier["max_minutes"]:
            return {"duration_minutes": duration_minutes, "amount_due": tier["fee"]}


def quote_exit_fee(plate):
    """Read-only lookup used by both the console and the web 'Get amount due' step."""
    with state_lock:
        if plate not in plate_map:
            return {"success": False, "message": "Vehicle not recognized"}
        bill_result = calculate_fee(plate)

    return {"success": True, "amount_due": bill_result["amount_due"], "duration_minutes": bill_result["duration_minutes"]}


# ---------------------------------------------------------------------------
# MODULE 6: Reporting / Audit Trail
# (placed before Module 5 so vehicle_exit-related functions can call it)
# ---------------------------------------------------------------------------
# Append-only log of every completed, paid transaction -- satisfies the
# client requirement to produce an auditable record for reconciliation
# and VAT. Records are only ever added, never edited or removed.
AUDIT_LOG_FILE = "audit_log.csv"
AUDIT_HEADERS = ["plate", "slot", "arrival_time", "exit_time", "amount_paid", "payment_method", "logged_at"]


def log_transaction(plate, slot_number, arrival_time, exit_time, amount_paid, payment_method):
    file_exists_already = False
    try:
        with open(AUDIT_LOG_FILE, "r"):
            file_exists_already = True
    except FileNotFoundError:
        file_exists_already = False

    with open(AUDIT_LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists_already:
            writer.writerow(AUDIT_HEADERS)
        writer.writerow([plate, slot_number, arrival_time, exit_time, amount_paid, payment_method, datetime.now()])


def build_report_data():
    """Administrative reporting: totals collected and a breakdown by payment method."""
    try:
        with open(AUDIT_LOG_FILE, "r", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
    except FileNotFoundError:
        rows = []

    total_collected = 0.0
    count_by_method = {}
    for row in rows:
        try:
            amount = float(row["amount_paid"])
        except (ValueError, KeyError):
            continue  # skip a malformed row rather than crashing the report
        total_collected += amount
        method = row.get("payment_method", "Unknown")
        count_by_method[method] = count_by_method.get(method, 0) + 1

    return {
        "total_transactions": len(rows),
        "total_collected": round(total_collected, 2),
        "by_method": count_by_method
    }


def generate_report():
    """Console version of the report -- prints what build_report_data() returns."""
    report = build_report_data()

    if report["total_transactions"] == 0:
        print("\nNo transactions recorded yet.")
        return

    print("\n--- SmartPark KE: Collections Report ---")
    print(f"Total transactions: {report['total_transactions']}")
    print(f"Total collected: Kshs {report['total_collected']:.2f}")
    print("By payment method:")
    for method, count in report["by_method"].items():
        print(f"  {method}: {count} transaction(s)")


# ---------------------------------------------------------------------------
# MODULE 5: Exit / Barrier Control
# ---------------------------------------------------------------------------
PAYMENT_METHODS = {"1": "M-Pesa", "2": "Card", "3": "Cash"}


def select_payment_method():
    while True:
        print("Select payment method: 1) M-Pesa  2) Card  3) Cash")
        choice = input("Choice: ").strip()
        if choice in PAYMENT_METHODS:
            return PAYMENT_METHODS[choice]
        print("Invalid choice, please enter 1, 2, or 3.")


def complete_exit(plate, payment_method, amount_received):
    """
    Core exit logic shared by the console and the web dashboard: checks
    payment, logs the transaction, frees the slot, and opens the barrier.
    """
    with state_lock:
        if plate not in plate_map:
            return {"success": False, "message": "Vehicle not recognized"}

        bill_result = calculate_fee(plate)
        amount_due = bill_result["amount_due"]

        if amount_due == 0:
            payment_method = "N/A (free)"
            payment_confirmed = True
        else:
            payment_confirmed = amount_received >= amount_due

        if not payment_confirmed:
            return {
                "success": False,
                "message": "Payment failed. Barrier remains closed.",
                "amount_due": amount_due
            }

        slot_number = plate_map[plate]
        arrival_time = slot_map[slot_number]["arrival_time"]
        exit_time = datetime.now()

        log_transaction(plate, slot_number, arrival_time, exit_time, amount_due, payment_method)  # Module 6

        free_slot(plate)
        available_slot_queue.append(slot_number)

    return {
        "success": True,
        "message": "Barrier open. Please drive through.",
        "amount_due": amount_due,
        "payment_method": payment_method
    }


def vehicle_exit(plate):
    """Console version: prompts for payment method/amount, then delegates to complete_exit()."""
    quote = quote_exit_fee(plate)
    if not quote["success"]:
        print(quote["message"])
        return False

    amount_due = quote["amount_due"]

    if amount_due == 0:
        method = "N/A (free)"
        amount_received = 0
    else:
        method = select_payment_method()
        print(f"Amount due: Kshs {amount_due} via {method}")
        while True:
            raw_amount = input("Enter amount received: ").strip()
            try:
                amount_received = float(raw_amount)
                break
            except ValueError:
                print("That's not a valid number. Please try again.")

    result = complete_exit(plate, method, amount_received)
    print(result["message"])
    return result["success"]


def simulate_earlier_arrival(plate, minutes_ago):
    """
    TESTING/DEMO ONLY -- not a client requirement. Lets you back-date a
    parked vehicle's arrival time so you can see the paid-exit flow (and
    each fee tier) without waiting hours in real time.
    """
    with state_lock:
        if plate not in plate_map:
            return {"success": False, "message": "That plate is not currently parked."}
        slot_number = plate_map[plate]
        slot_map[slot_number]["arrival_time"] = datetime.now() - timedelta(minutes=minutes_ago)

    return {"success": True, "message": f"OK: back-dated by {minutes_ago} minutes (for testing)."}


# ---------------------------------------------------------------------------
# WEB API: bridges the interactive dashboard to the modules above
# ---------------------------------------------------------------------------
class SmartParkRequestHandler(http.server.SimpleHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/dashboard.html"
        elif self.path == "/api/status":
            with state_lock:
                snapshot = build_status_snapshot()
            self._send_json(200, snapshot)
            return
        elif self.path == "/api/report":
            report = build_report_data()
            self._send_json(200, report)
            return

        return super().do_GET()  # serves dashboard.html and any other static files

    def do_POST(self):
        data = self._read_json_body()

        if self.path == "/api/entry":
            plate = str(data.get("plate", "")).strip()
            if not plate:
                self._send_json(400, {"success": False, "message": "Plate number is required"})
                return
            result = vehicle_entry(plate)
            self._send_json(200 if result["success"] else 409, result)
            return

        if self.path == "/api/exit/quote":
            plate = str(data.get("plate", "")).strip()
            result = quote_exit_fee(plate)
            self._send_json(200 if result["success"] else 404, result)
            return

        if self.path == "/api/exit/pay":
            plate = str(data.get("plate", "")).strip()
            method = str(data.get("method", "")).strip()
            try:
                amount_received = float(data.get("amount_received", 0))
            except (TypeError, ValueError):
                self._send_json(400, {"success": False, "message": "Invalid amount received"})
                return
            result = complete_exit(plate, method, amount_received)
            self._send_json(200 if result["success"] else 402, result)
            return

        if self.path == "/api/simulate-arrival":
            plate = str(data.get("plate", "")).strip()
            try:
                minutes_ago = float(data.get("minutes_ago", 0))
            except (TypeError, ValueError):
                self._send_json(400, {"success": False, "message": "Invalid minutes"})
                return
            result = simulate_earlier_arrival(plate, minutes_ago)
            self._send_json(200 if result["success"] else 404, result)
            return

        self._send_json(404, {"success": False, "message": "Unknown endpoint"})

    def log_message(self, format, *args):
        pass  # suppress per-request access log lines so the console menu stays readable


# ---------------------------------------------------------------------------
# MENU / MAIN PROGRAM (console -- an alternative to the web dashboard;
# both operate on the same shared state)
# ---------------------------------------------------------------------------
def main():
    initialize_slots(20)  # change lot size here if the assignment specifies one
    start_dashboard_server()

    while True:
        print("\n--- SmartPark KE (console) ---")
        print(f"Available slots: {get_available_count()}")
        print("1. View available slots")
        print("2. Vehicle entry")
        print("3. Vehicle exit")
        print("4. Generate collections report")
        print("5. Quit")
        print("6. [TESTING ONLY] Simulate earlier arrival, to test paid exits")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            print("Free slots:", get_available_slots())
        elif choice == "2":
            plate = input("Enter plate number: ").strip()
            print(vehicle_entry(plate)["message"])
        elif choice == "3":
            plate = input("Enter plate number: ").strip()
            vehicle_exit(plate)
        elif choice == "4":
            generate_report()
        elif choice == "5":
            print("Shutting down SmartPark KE.")
            break
        elif choice == "6":
            plate = input("Plate number (already parked): ").strip()
            try:
                minutes_ago = float(input("Simulate how many minutes ago it arrived: ").strip())
                print(simulate_earlier_arrival(plate, minutes_ago)["message"])
            except ValueError:
                print("Please enter a valid number of minutes.")
        else:
            print("Invalid option, try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down SmartPark KE.")
