# Brake dynamometer test evaluation: friction behaviour, fade and particulate estimate (self study after a data analysis short course)

Python evaluation chain for brake dynamometer stops with a SQLite test database and an Excel overview.
**All test data are synthetic** and every material, geometry and emission value is assumed.

## What it does
1. Simulates 55 brake stops on an inertia dynamometer: 30 characteristic stops (pressure sweep 10 to 60 bar),
   15 high energy fade stops with short pauses, 10 recovery stops. Channels at 100 Hz: speed, pressure, torque, disc temperature.
2. Evaluates the friction coefficient of every stop from measured torque and pressure, averaged over 10 to 80 percent of the stop.
3. Derives the friction behaviour: mean mu per section, minimum mu in fade, fade drop, pressure sensitivity.
4. Estimates wear mass from dissipated energy (higher factor above 300 deg C) and airborne PM10 as an assumed share of wear.
5. Stores stops and samples (every 5th) in `results/brake_test_database.sqlite`, builds the section overview by SQL and exports
   `results/brake_overview.xlsx` and `.csv`, plus `results/mu_and_temperature.png`.

Run `python src/brake_eval.py` and `python -m pytest`.

## Results of the run (`results/summary.json`)
- 55 stops, mean mu 0.41 in the characteristic section, minimum 0.36 in fade (about 12% drop), recovery mean 0.41.
- Maximum disc temperature about 325 deg C, pressure sensitivity about -0.0007 per bar.
- Evaluated mu within 0.32% of the generating model on every stop.
- PM10 estimate about 2.3 g over the program, 315 mg/MJ in normal stops and 441 mg/MJ in fade.

## Assumed data (placeholders, not measured, not from a datasheet)
Piston area, friction radius, rolling radius, simulated vehicle mass per corner, disc mass and specific heat, cooling constant,
the friction model (mu0 0.42, temperature and pressure sensitivity, fade above 380 deg C), wear 0.9 mg/kJ with factor 2.5 above
300 deg C, PM10 share 0.35. All in `src/brake_eval.py`.

## Limits
- The PM10 numbers follow directly from the assumed wear factor and PM10 share. They show the bookkeeping, not real emissions.
  Real particulate measurement needs a sampling tunnel and particle counting, which this study does not model.
- The program is simplified and not SAE J2522, AK Master or a WLTP brake cycle.
- No pad compressibility, no bedding, no humidity, no disc thermal gradients, no real sensor data.
