const STATUSES = ["available", "occupied", "reserved", "maintenance"];
const slots = Array.from({ length: 24 }, (_, i) => ({
  id: `S${String(i + 1).padStart(2, "0")}`,
  status: "available",
  vehiclePlate: ""
}));

function randomizeInitialState() {
  slots.forEach((slot) => {
    const n = Math.random();
    if (n < 0.58) {
      slot.status = "available";
      slot.vehiclePlate = "";
    } else if (n < 0.82) {
      slot.status = "occupied";
      slot.vehiclePlate = generatePlate();
    } else if (n < 0.93) {
      slot.status = "reserved";
      slot.vehiclePlate = "";
    } else {
      slot.status = "maintenance";
      slot.vehiclePlate = "";
    }
  });
}

function generatePlate() {
  const a = String.fromCharCode(65 + Math.floor(Math.random() * 26));
  const b = String.fromCharCode(65 + Math.floor(Math.random() * 26));
  const c = String.fromCharCode(65 + Math.floor(Math.random() * 26));
  const n = Math.floor(100 + Math.random() * 900);
  return `${a}${b}${c} ${n}`;
}

function summarize() {
  return STATUSES.reduce(
    (acc, status) => {
      acc[status] = slots.filter((slot) => slot.status === status).length;
      return acc;
    },
    { total: slots.length }
  );
}

function autoRefresh() {
  const available = slots.filter((slot) => slot.status === "available");
  const occupied = slots.filter((slot) => slot.status === "occupied");
  if (available.length > 0 && Math.random() < 0.4) {
    const target = available[Math.floor(Math.random() * available.length)];
    target.status = "occupied";
    target.vehiclePlate = generatePlate();
  } else if (occupied.length > 0 && Math.random() < 0.4) {
    const target = occupied[Math.floor(Math.random() * occupied.length)];
    target.status = "available";
    target.vehiclePlate = "";
  }
}

function parkVehicle(plate) {
  const cleanPlate = plate.trim().toUpperCase();
  if (!cleanPlate) {
    return "Please provide a vehicle plate number.";
  }

  const slot = slots.find((candidate) => candidate.status === "available");
  if (!slot) {
    return "No available slots right now.";
  }

  slot.status = "occupied";
  slot.vehiclePlate = cleanPlate;
  return `Vehicle ${cleanPlate} parked at ${slot.id}.`;
}

function releaseSlot(slotId) {
  const slot = slots.find((candidate) => candidate.id === slotId);
  if (!slot || slot.status !== "occupied") {
    return "Slot cannot be released.";
  }
  slot.status = "available";
  slot.vehiclePlate = "";
  return `Slot ${slot.id} released.`;
}

function render() {
  const statsEl = document.getElementById("stats");
  const gridEl = document.getElementById("slotGrid");
  const filter = document.getElementById("statusFilter").value;
  const summary = summarize();

  statsEl.innerHTML = Object.entries(summary)
    .map(([key, value]) => `<div class="stat"><strong>${key}</strong><div>${value}</div></div>`)
    .join("");

  gridEl.innerHTML = slots
    .filter((slot) => filter === "all" || slot.status === filter)
    .map((slot) => {
      const releaseButton =
        slot.status === "occupied"
          ? `<button data-release="${slot.id}">Release</button>`
          : "";

      return `
        <article class="slot ${slot.status}">
          <h3>${slot.id}</h3>
          <span class="badge">${slot.status}</span>
          <p>${slot.vehiclePlate || "-"}</p>
          ${releaseButton}
        </article>
      `;
    })
    .join("");
}

function setMessage(msg) {
  document.getElementById("message").textContent = msg;
}

function runSelfTest() {
  const testSlots = [
    { id: "A1", status: "available", vehiclePlate: "" },
    { id: "A2", status: "occupied", vehiclePlate: "KDA 123A" },
    { id: "A3", status: "reserved", vehiclePlate: "" },
    { id: "A4", status: "maintenance", vehiclePlate: "" }
  ];
  const summary = STATUSES.reduce(
    (acc, status) => {
      acc[status] = testSlots.filter((slot) => slot.status === status).length;
      return acc;
    },
    { total: testSlots.length }
  );

  if (
    summary.total !== 4 ||
    summary.available !== 1 ||
    summary.occupied !== 1 ||
    summary.reserved !== 1 ||
    summary.maintenance !== 1
  ) {
    throw new Error("Self-test failed for slot summary logic.");
  }
}

function setup() {
  randomizeInitialState();
  runSelfTest();
  render();

  document.getElementById("parkBtn").addEventListener("click", () => {
    const input = document.getElementById("plateInput");
    setMessage(parkVehicle(input.value));
    input.value = "";
    render();
  });

  document.getElementById("statusFilter").addEventListener("change", render);

  document.getElementById("slotGrid").addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const slotId = target.dataset.release;
    if (!slotId) {
      return;
    }
    setMessage(releaseSlot(slotId));
    render();
  });

  setInterval(() => {
    autoRefresh();
    render();
  }, 5000);
}

setup();
