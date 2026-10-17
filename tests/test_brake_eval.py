import sys, pathlib, sqlite3
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import numpy as np, brake_eval as b

def test_noise_free_stop_recovers_model_mu():
    old = (b.NOISE_MU, b.NOISE_P); b.NOISE_MU, b.NOISE_P = 1e-12, 0.0
    try:
        ch, _ = b.run_stop(np.random.default_rng(0), 80, 30, 30, 100.0)
        mu, p, T = b.evaluate_stop(ch)
        assert abs(mu - b.mu_true(T, 30)) / b.mu_true(T, 30) < 0.01
    finally:
        b.NOISE_MU, b.NOISE_P = old

def test_energy_balance_heats_the_disc():
    ch, T_end = b.run_stop(np.random.default_rng(1), 100, 5, 40, 40.0)
    assert T_end > 40.0 + 20.0

def test_database_and_summary(tmp_path):
    b.OUT = tmp_path
    s = b.main()
    con = sqlite3.connect(tmp_path / "brake_test_database.sqlite")
    assert con.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == len(b.program())
    assert s["max_eval_error_vs_model_pct"] < 2.0 and s["mu_fade_min"] < s["mu_characteristic_mean"]
