# Engineering methods

All methods are preliminary-design methods. Each result in the app and report lists its own inputs, equations, assumptions and warnings. This file records the reasoning and the limitations.

## A. Fundamentals (`ecalc/calc/fundamentals.py`)
Only power-factor correction is exposed in the app (Extra tools). The other functions remain in the engine, are tested, and are used internally (e.g. inverter current).
| Calculation | Method |
|---|---|
| Ohm's law | V = IR, P = VI (exactly two inputs; resistive circuit) |
| 1-phase power | S = VI, P = S cos φ, Q = S sin φ (sign by lagging/leading) |
| 3-phase power | S = √3 V_LL I (balanced, sinusoidal) |
| Load current | I = P / (V cos φ) or P / (√3 V_LL cos φ) |
| PF correction | Qc = P (tan φ1 − tan φ2); C per phase = Qc / (3ωV_LL²) for delta, Qc / (ωV_LL²) for star |
| PF from meter readings | PF_avg = kWh / √(kWh² + kVArh²); sizing uses maximum demand kW (not the average) |
| Energy | E = P × h × days; cost = E × flat tariff |
| Conversions | hp = 0.745699872 kW; metric hp = 0.73549875 kW; kWh = 3.6 MJ; AWG d = 0.127 mm × 92^((36−n)/39); kcmil × 0.506707479 = mm² |

Limitations: no harmonics, no unbalance, no tariff slabs or demand charges. PF correction warns about resonance and detuning.

## B. Solar PV (`ecalc/calc/solar.py`, `ecalc/solar_data.py`)
- **Resource:** either (1) PVGIS v5.3 `PVcalc` for 1 kWp at the user's latitude, longitude, tilt and azimuth, with the user's system-loss percentage, returning annual and monthly kWh/kWp with losses already applied; or (2) user-entered peak sun hours, with Y = PSH × 365 × (1 − losses). The source string is printed in every result. No solar data is invented: if PVGIS is unreachable, the user must enter PSH from a reliable dataset.
- **Losses:** with PVGIS the entered loss is the *system* loss only (PVGIS default 14%); PVGIS separately applies reflection, spectral and temperature losses (Kathmandu: −2.6%, −0.4%, −7.9%; total −23.2%, PR = 0.768). With peak sun hours the entered value is the *total* loss, so the app defaults to 23% (PR ≈ 0.77) instead of 14%, which would overestimate generation by about 10%.
- **Sizing:** kWp = annual demand × target% / Y; panels = ceil(kWp × 1000 / Wp); area check against the user's net module area.
- **Inverter:** AC kW = kWp / DC:AC ratio (a user design choice, default 1.2). For hybrid systems it is raised to the peak simultaneous load if that is entered. Surge is not checked (warning given).
- **Battery:** usable = backup kWh/day × autonomy days; nominal = usable / DoD / η(battery→AC); Ah = nominal × 1000 / V_bank. Usable and nominal are always shown separately.
- **Economics:** saving = min(E_gen, E_demand) × tariff + excess × export rate (annual netting). Simple payback = user-entered capex / saving. Not calculated if tariff or cost is missing.
- **Not modelled:** hourly self-consumption, shading, row spacing, degradation, tariff escalation, temperature effects beyond PVGIS, string/MPPT voltage design. The existing off-grid tool (`../solar-sizing-tool`) covers surge and DC cable checks for off-grid systems.
- **Cross-check:** for Kathmandu (27.7172 N, 85.324 E, 27° tilt, south, 14% loss), PVGIS returned E_y = 1426.64 kWh/kWp/yr (ERA5, 2005–2023). The monthly values sum to the annual value within 0.5% (tested). That is about 3.9 kWh/kWp/day, which is in the expected range for the Kathmandu valley.

## Load schedule (`ecalc/calc/loads.py`)
- Connected kW = Σ W × qty / 1000; daily kWh = Σ W × qty × h / 1000.
- Maximum demand = connected kW × **coincidence (simultaneity) factor** (≤ 1, default 1.0). The textbook **diversity factor** (Σ individual max demands / group max demand, ≥ 1) is its inverse and is printed alongside.
- The factor affects peak kW and hybrid inverter sizing only, never energy. Values below 1 with fewer than 10 load types trigger an undersizing warning.

## C. Cable voltage drop (`ecalc/calc/cable.py`)
- R_20 is taken from the IEC 60228 Table 2 maximum conductor resistance (class 2; copper 0.75–300 mm², aluminium 16–300 mm²). This is more conservative than ρ/A because it includes stranding.
- Temperature: R_T = R_20 (1 + α20 (T − 20)), α20 = 0.00393 (Cu), 0.00403 (Al).
- ΔV: DC 2IRL; 1-phase 2IL(R cos φ + X sin φ); 3-phase √3 IL(R cos φ + X sin φ). X is user-entered from the datasheet (default 0 with a warning for ≥ 35 mm²).
- Minimum size by drop: the first standard size meeting the limit, with a comparison table.
- **Not checked:** ampacity, derating (ambient, grouping, installation method), protection coordination, short-circuit withstand, earth-fault loop impedance. Every result says so.

## D. Power-system study preparation: not implemented
No load-flow, short-circuit or protection-coordination results are produced. ETAP, PowerFactory or similar outputs are never fabricated.

## Reference values used in tests (hand calculations)
| Case | Hand result |
|---|---|
| 3φ 400 V, 10 A, PF 0.8 | S = 6.928 kVA, P = 5.543 kW, Q = 4.157 kvar |
| 15 kW, 400 V, PF 0.85, 3φ | I = 25.47 A |
| 100 kW, PF 0.70 → 0.95 | Qc = 69.15 kvar; C = 458.6 µF/phase (delta, 400 V, 50 Hz) |
| 1φ 230 V, 20 A, 30 m, 4 mm² Cu, 70 °C | R = 5.516 Ω/km, ΔV = 6.619 V = 2.878% |
| 3φ 400 V, 50 A, 100 m, 16 mm² Cu, PF 0.85, X 0.08 mΩ/m | ΔV = 10.49 V = 2.62% |
| 10 kWh/day, PSH 5, 20% loss, 550 Wp | Y = 1460, 2.5 kWp needed, 5 panels, 4015 kWh/yr |
| 5 kWh backup, DoD 80%, η 95%, 48 V | 6.579 kWh nominal, 137.1 Ah |
