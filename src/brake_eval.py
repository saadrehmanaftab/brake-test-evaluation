"""Brake dynamometer test evaluation: friction behaviour, fade and a wear based particulate estimate.

SELF INITIATED STUDY. All test data are SYNTHETIC, generated from an assumed friction model, an assumed
brake geometry, an assumed thermal model and assumed wear and emission factors (see ASSUMED INPUTS and
README). The test program is a simplified sequence loosely in the spirit of characteristic, fade and
recovery sections. It is not SAE J2522, AK Master or WLTP brake cycle, and its results are not comparable
with those procedures.

Run: python src/brake_eval.py   (writes results/ and results/brake_test_database.sqlite)
"""
import json, pathlib, sqlite3
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1] / "results"

# ------------------------------------------------------------------ ASSUMED INPUTS
A_PISTON = 2.4e-3        # total piston area per side, m^2 (clamp force = p * A)
R_EFF = 0.11             # effective friction radius, m
R_WHEEL = 0.31           # rolling radius, m
M_VEH = 450.0            # vehicle mass per braked corner, kg (inertia simulated on the dyno)
M_DISC, CP = 6.0, 460.0  # disc mass kg, specific heat J/(kg K)
H_COOL = 0.006           # Newton cooling constant of the disc, 1/s
T_AMB = 40.0             # ambient and start temperature, deg C
FS = 100.0               # sample rate, Hz
MU0, KT, KP = 0.42, 6.0e-4, 1.5e-3   # friction model: mu0, temperature and pressure sensitivity
T_FADE, K_FADE = 380.0, 1.6e-3       # extra fade above T_FADE, per K
WEAR_MG_PER_KJ = 0.9     # pad and disc wear mass per kJ dissipated, below 300 deg C
WEAR_HOT_FACTOR = 2.5    # wear factor above 300 deg C
PM10_SHARE = 0.35        # share of wear mass emitted as airborne PM10
NOISE_MU, NOISE_P = 0.008, 0.2       # measurement noise: torque derived mu and pressure (bar)
SEED = 11

def mu_true(T, p_bar):
    mu = MU0 * (1 - KT * (T - 100.0)) * (1 - KP * (p_bar - 30.0))
    return mu * (1 - K_FADE * max(0.0, T - T_FADE))

def program():
    """Section name, v_start km/h, v_end km/h, pressure bar, pause s between stops."""
    stops = []
    for k in range(30):                       # characteristic section: pressure sweep at moderate energy
        stops.append(("characteristic", 80, 30, [10, 20, 30, 40, 50, 60][k % 6], 60))
    for k in range(15):                       # fade section: high energy stops with short pauses
        stops.append(("fade", 100, 5, 40, 35))
    for k in range(10):                       # recovery section
        stops.append(("recovery", 80, 30, 30, 120))
    return stops

def run_stop(rng, v0, v1, p_bar, T0):
    """Integrate one stop sample by sample. Returns channels and end temperature."""
    dt = 1 / FS; v = v0 / 3.6; T = T0; rows = []
    while v > v1 / 3.6:
        p = p_bar + rng.normal(0, NOISE_P)
        mu = mu_true(T, p_bar)
        torque = 2 * mu * p * 1e5 * A_PISTON * R_EFF               # two pad interfaces
        decel = torque / R_WHEEL / M_VEH
        power = torque * v / R_WHEEL                               # W into the disc
        T += (power / (M_DISC * CP) - H_COOL * (T - T_AMB)) * dt
        rows.append((v * 3.6, p, torque * (1 + rng.normal(0, NOISE_MU / max(mu, 1e-6))), T))
        v -= decel * dt
    return np.array(rows), T

def evaluate_stop(ch):
    """Mean friction coefficient over 10 to 80 percent of the stop, from measured torque and pressure."""
    n = len(ch); s = slice(int(0.1 * n), int(0.8 * n))
    v, p, tq, T = ch[s].T
    mu = tq / (2 * p * 1e5 * A_PISTON * R_EFF)
    return float(mu.mean()), float(p.mean()), float(T.mean())

def main():
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    db = OUT / "brake_test_database.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE stops(stop INTEGER PRIMARY KEY, section TEXT, v_start REAL, v_end REAL, p_set_bar REAL,
                       mu_eval REAL, mu_model REAL, p_mean_bar REAL, T_mean_C REAL, T_end_C REAL,
                       energy_kJ REAL, wear_mg REAL, pm10_mg REAL);
    CREATE TABLE samples(stop INTEGER, i INTEGER, v_kmh REAL, p_bar REAL, torque_Nm REAL, T_C REAL);
    """)
    T = T_AMB; recs = []
    for k, (sec, v0, v1, p_set, pause) in enumerate(program(), start=1):
        ch, T_end = run_stop(rng, v0, v1, p_set, T)
        mu_e, p_m, T_m = evaluate_stop(ch)
        energy = 0.5 * M_VEH * ((v0 / 3.6) ** 2 - (v1 / 3.6) ** 2) / 1000
        wear = WEAR_MG_PER_KJ * energy * (WEAR_HOT_FACTOR if T_m > 300 else 1.0)
        pm10 = PM10_SHARE * wear
        r = (k, sec, v0, v1, p_set, mu_e, mu_true(T_m, p_set), p_m, T_m, T_end, energy, wear, pm10)
        con.execute("INSERT INTO stops VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
        con.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?)",
                        [(k, i, *map(float, row)) for i, row in enumerate(ch[::5])])
        recs.append(r)
        T = T_AMB + (T_end - T_AMB) * np.exp(-H_COOL * pause)       # cooling during the pause
    con.commit()

    st = pd.read_sql_query("SELECT * FROM stops", con)
    overview = pd.read_sql_query("""
        SELECT section, COUNT(*) AS stops, AVG(mu_eval) AS mu_mean, MIN(mu_eval) AS mu_min, MAX(mu_eval) AS mu_max,
               MAX(T_end_C) AS T_max_C, SUM(energy_kJ) AS energy_kJ, SUM(pm10_mg) AS pm10_mg
        FROM stops GROUP BY section ORDER BY MIN(stop)""", con)
    overview["pm10_mg_per_MJ"] = overview.pm10_mg / (overview.energy_kJ / 1000)
    ch = st[st.section == "characteristic"]
    slope = float(np.polyfit(ch.p_mean_bar, ch.mu_eval, 1)[0])            # pressure sensitivity per bar
    eval_err = float((100 * (st.mu_eval - st.mu_model).abs() / st.mu_model).max())
    with pd.ExcelWriter(OUT / "brake_overview.xlsx") as xw:
        overview.to_excel(xw, sheet_name="overview", index=False)
        st.to_excel(xw, sheet_name="stops", index=False)
    overview.to_csv(OUT / "brake_overview.csv", index=False)
    con.close()

    green = overview.set_index("section")
    summary = dict(
        stops=int(len(st)),
        mu_characteristic_mean=float(green.loc["characteristic", "mu_mean"]),
        mu_fade_min=float(green.loc["fade", "mu_min"]),
        fade_drop_pct=float(100 * (1 - green.loc["fade", "mu_min"] / green.loc["characteristic", "mu_mean"])),
        mu_recovery_mean=float(green.loc["recovery", "mu_mean"]),
        T_max_C=float(st.T_end_C.max()),
        pressure_sensitivity_per_bar=slope,
        max_eval_error_vs_model_pct=eval_err,
        pm10_total_mg=float(st.pm10_mg.sum()),
        pm10_mg_per_MJ_characteristic=float(green.loc["characteristic", "pm10_mg_per_MJ"]),
        pm10_mg_per_MJ_fade=float(green.loc["fade", "pm10_mg_per_MJ"]),
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 3.6)); ax2 = ax.twinx()
        ax.plot(st.stop, st.mu_eval, "o", ms=3, label="evaluated mu"); ax.set_ylabel("friction coefficient mu")
        ax2.plot(st.stop, st.T_end_C, "r-", lw=0.8, label="disc temperature"); ax2.set_ylabel("disc temperature, deg C")
        ax.set_xlabel("stop number"); fig.tight_layout(); fig.savefig(OUT / "mu_and_temperature.png", dpi=130)
    except Exception as ex:
        print("plot skipped", ex)
    return summary

if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
