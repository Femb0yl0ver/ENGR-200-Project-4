import math
import pandas as pd
import streamlit as st

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="Union City Water System Simulator",
    page_icon="🚰",
    layout="wide",
)

# Configuration Parameters
P = {
    "n": 5,
    "capH": 30,
    "pumpX": 1.3,
    "fuelH": 96.0,
    "seg": 0.1,
}

# --- Sidebar Controls ---
st.sidebar.title("🎛️ Simulation Controls")

population = st.sidebar.number_input(
    "Population", min_value=1000, value=70000, step=1000
)
gpcd = st.sidebar.number_input(
    "Gallons / Person / Day", min_value=20, value=120, step=5
)
grid_on = st.sidebar.toggle("Power Grid Active", value=True)
sim_hours = st.sidebar.slider(
    "Simulation Duration (Hours)",
    min_value=1,
    max_value=168,
    value=24,
    step=1,
)

st.sidebar.subheader("Zone Fault Injections")
failed_pumps = []
contaminated_zones = []

for i in range(P["n"]):
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.checkbox(f"Fail Pump Z{i+1}", key=f"p_{i}"):
            failed_pumps.append(i)
    with col2:
        if st.checkbox(f"Contaminate Z{i+1}", key=f"c_{i}"):
            contaminated_zones.append(i)


# --- Simulation Model ---
class Zone:

    def __init__(self, avg_demand: float):
        self.avg = avg_demand
        self.cap = avg_demand * 60 * P["capH"]
        self.tank = self.cap * 0.95
        self.pump = True
        self.con = False
        self.fuel = float(P["fuelH"])
        self.on = True
        self.out = False
        self.need = avg_demand
        self.inflow = avg_demand


def run_simulation(
    pop: float,
    gpcd_val: float,
    grid_active: bool,
    hours: int,
    failed_p: list,
    contam_z: list,
):
    avg_gpm = (pop * gpcd_val) / 1440 / P["n"]
    zones = [Zone(avg_gpm) for _ in range(P["n"])]

    for idx in failed_p:
        zones[idx].pump = False
    for idx in contam_z:
        zones[idx].con = True

    history = []
    dt = 15  # 15-minute time steps
    steps = int((hours * 60) / dt)
    clock = 0.0

    for step in range(steps):
        h = (clock / 60.0) % 24
        mult = 1.0 + 0.3 * math.sin(2 * math.pi * (h - 13) / 24)

        for z in zones:
            if not grid_active:
                z.fuel = max(0.0, z.fuel - (dt / 60.0))
            z.on = grid_active or (z.fuel > 0)
            z.need = z.avg * mult * ((1.0 - P["seg"]) if z.con else 1.0)
            z.inflow = (z.avg * P["pumpX"]) if (z.pump and z.on) else 0.0
            z.tank += (z.inflow - z.need) * dt

        # Interties
        for i in range(P["n"]):
            j = (i + 1) % P["n"]
            a, b = zones[i], zones[j]
            if not a.con and not b.con:
                d = (a.tank / a.cap) - (b.tank / b.cap)
                if abs(d) > 0.02:
                    f = max(-0.8, min(0.8, d * 4.0)) * a.avg
                    src = a if f > 0 else b
                    max_transfer = (max(0.0, src.tank) / dt) * 0.5
                    f = math.copysign(min(abs(f), max_transfer), f)
                    a.tank -= f * dt
                    b.tank += f * dt

        for z in zones:
            z.tank = min(z.cap, max(0.0, z.tank))
            z.out = (z.tank <= 1.0) and (z.inflow < z.need)

        record = {"Time (h)": clock / 60.0}
        for i, z in enumerate(zones):
            record[f"Zone {i+1} Tank (%)"] = (z.tank / z.cap) * 100
        history.append(record)

        clock += dt

    return pd.DataFrame(history), zones, avg_gpm


# Run simulation
df_results, final_zones, avg_demand = run_simulation(
    population, gpcd, grid_on, sim_hours, failed_pumps, contaminated_zones
)

# --- Main Dashboard Visuals ---
st.title("🚰 Union City Zoned Water System Simulator")
st.markdown(
    "Interactive model testing zone redundancy, intertie sharing, and power outage resilience."
)

# Requirement Metrics Header
total_tank = sum(z.tank for z in final_zones)
storage_hrs = total_tank / (avg_demand * P["n"] * 60)

affected_pct = 0.0
for z in final_zones:
    if z.out:
        affected_pct += 100 / P["n"]
    elif z.con:
        affected_pct += (100 / P["n"]) * P["seg"]

m1, m2, m3 = st.columns(3)
m1.metric("System Storage Capacity", f"{storage_hrs:.1f} Hours", delta="Target: >= 24h")
m2.metric(
    "Unserved / Contaminated Pop",
    f"{affected_pct:.1f}%",
    delta="Target: <= 5%",
    delta_color="inverse",
)
m3.metric(
    "Grid Power Status",
    "ONLINE" if grid_on else "OFF-GRID",
    delta="Backup Running" if not grid_on else "Normal Operations",
)

st.divider()

# Zone Status Cards
st.subheader("Current Zone Levels & Status")
cols = st.columns(P["n"])

for i, col in enumerate(cols):
    z = final_zones[i]
    pct = (z.tank / z.cap) * 100
    with col:
        st.write(f"### Zone {i+1}")
        st.progress(int(pct) / 100)
        st.write(f"**Tank:** {pct:.1f}%")
        st.write(f"**Demand:** {z.need:.0f} gpm")
        st.write(f"**Pump:** {'🟢 Active' if (z.pump and z.on) else '🔴 Failure'}")
        st.write(f"**Fuel:** {z.fuel:.1f}h")

st.divider()

# Charting
st.subheader("Tank Level Trends Over Time")
st.line_chart(df_results.set_index("Time (h)"))