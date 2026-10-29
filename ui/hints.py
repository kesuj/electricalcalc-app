"""Input hints shared by all pages: (placeholder shown inside the empty box, longer help on the '?' icon).

Placeholders say where to find or how to measure each value. Typical ranges are guidance only;
the user must enter the value for their own project.
"""

H: dict[str, tuple[str, str]] = {
    # ---- site / solar resource ---------------------------------------------------------------
    "loss_pvgis": ("Typically 14",
                   "Losses PVGIS does NOT model: cable resistance (1-3%), inverter (2-4%), dust/soiling (2-5%), "
                   "mismatch (1-2%), ageing. PVGIS adds temperature and reflection losses itself. "
                   "Clean, short wiring: 10-12. Dusty site, long cables: 16-20."),
    "loss_psh": ("Typically 20-25",
                 "With peak sun hours nothing else is deducted, so include everything: temperature (~8%), "
                 "reflection (~3%) plus cables/inverter/dust (~14%). About 23% total = performance ratio 0.77."),
    "lat": ("From Google Maps",
            "Open Google Maps, right-click the exact roof, click the coordinates to copy. The first number is "
            "latitude (e.g. 27.7172 for Kathmandu). Leave empty to use the chosen city's coordinates."),
    "lon": ("From Google Maps",
            "The second number from Google Maps (e.g. 85.3240 for Kathmandu). Leave empty to use the chosen city."),
    "tilt": ("Roof angle or ≈ latitude",
             "Flush on a sloped roof: measure the roof pitch with a phone inclinometer/angle-finder app. "
             "Mounting structure on a flat roof: a tilt close to the latitude gives the most yearly energy."),
    "azimuth": ("South 0, west 90, east -90",
                "Direction the panels FACE, using the PVGIS convention: 0 = due south, 90 = west, -90 = east, "
                "180 = north. Stand facing the panel front and read a phone compass (compass 180° = south = 0 here)."),
    "psh": ("globalsolaratlas.info",
            "Average daily solar energy on the tilted panel surface in kWh/m²/day (= peak sun hours). Look up the "
            "site on globalsolaratlas.info (GTI value) or PVGIS. Do not guess: it sets the whole design."),
    # ---- demand -------------------------------------------------------------------------------
    "coincidence": ("1.0 small building; 0.6-0.8 large",
                    "Share of the connected load running at the same moment. 1.0 = everything can run together "
                    "(safe for houses, shops, health posts). Large buildings with many loads: 0.6-0.8. Textbook "
                    "diversity factor is the inverse (e.g. 0.8 here = diversity 1.25). Affects peak kW and inverter size."),
    "monthly_kwh": ("Average of your bill units",
                    "On the NEA bill, 'units' = kWh. Add the units from the last 12 bills and divide by 12, so "
                    "seasonal changes (heaters, fans, pumps) are averaged."),
    "peak_kw": ("Max demand; optional",
                "Highest power drawn at one moment. Industrial/commercial bills show maximum demand. Otherwise add "
                "up the watts of everything that can run together and divide by 1000. Leave blank if unknown."),
    "backup": ("Σ W × hours ÷ 1000",
               "Energy the battery must supply per day: for each load needed during power cuts multiply watts × "
               "hours used during the outage, add them up, divide by 1000 → kWh/day."),
    # ---- system -------------------------------------------------------------------------------
    "offset": ("100 = all of it",
               "Percentage of the yearly consumption the solar should generate. 100 = all of it. Lower if roof "
               "space or budget is limited; above 100 only if exporting to the grid is allowed and paid."),
    "panel_wp": ("Datasheet Pmax",
                 "Rated power at STC printed on the panel label/datasheet as Pmax or 'Maximum power' (Wp)."),
    "panel_area": ("Length × width (m)",
                   "From the datasheet 'Dimensions': length (m) × width (m). A 2278 × 1134 mm panel = 2.58 m²."),
    "roof_area": ("Tape or Google Earth; optional",
                  "Usable roof area for panels in m² after leaving walkways and edge clearance. Measure with a tape "
                  "or Google Earth's ruler. Leave blank if space is not a constraint."),
    "dc_ac": ("Usually 1.1-1.3",
              "PV kWp ÷ inverter AC kW. Above 1 is normal because panels rarely reach full rating. Check the "
              "inverter datasheet's maximum DC input power."),
    "vbat": ("12 / 24 / 48 V",
             "Nominal voltage of the battery bank = the inverter's battery input voltage (inverter datasheet)."),
    "dod": ("Datasheet, e.g. 80",
            "Depth of discharge allowed by the battery warranty. Using more shortens battery life."),
    "autonomy": ("Days with no sun/grid",
                 "How many days the battery must supply the critical loads with no sun and no grid."),
    # ---- economics ----------------------------------------------------------------------------
    "tariff": ("From bill, e.g. 12",
               "Energy charge per kWh from the electricity bill (Rs/unit). For slab tariffs use the rate of the "
               "highest slab normally reached. Leave blank to skip savings."),
    "export": ("Optional",
               "Price the utility pays for exported energy (net-metering agreement). Blank = export not paid."),
    "cost_kwp": ("Installer quote",
                 "Total installed price of the PV system divided by its kWp, from a real quotation."),
    "bat_cost": ("Optional",
                 "Battery bank price divided by its nominal energy (V × Ah ÷ 1000)."),
    # ---- wiring -------------------------------------------------------------------------------
    "ac_len": ("Tape the cable route (m) +10%; blank = skip",
               "One-way route length of the inverter-to-main-board cable, following walls/trays, plus ~10% for "
               "bends. Leave blank to skip this check."),
    "ac_limit": ("Your spec/code; solar AC often 1-1.5",
                 "Allowed voltage drop for this cable as a % of nominal. IEC 60364 / BS 7671 allow 3% (lighting) / "
                 "5% (other) for the WHOLE installation, so one cable gets only part of it. Grid-tied inverters "
                 "see a voltage RISE and may trip on high voltage, so 1-1.5% is common."),
    "dc_len": ("Battery → inverter route (m); blank = skip", "One-way length of the battery cable."),
    "dc_limit": ("Often 1 (check manufacturer)",
                 "Allowed voltage drop on the battery cable. Low voltage + high current makes this cable critical; "
                 "follow the inverter/battery manual."),
    "temp": ("PVC 70 / XLPE 90",
             "Maximum conductor operating temperature from the cable datasheet (PVC usually 70 °C, XLPE 90 °C). "
             "Resistance is calculated at this temperature (conservative)."),
    "daily_kwh": ("Bill units ÷ 30",
                  "Average energy used per day in kWh. From the bill: monthly units ÷ 30. From appliances: add up "
                  "watts × hours for each and divide by 1000."),
    "backup_eng": ("kWh needed per day",
                   "Energy needed from the battery per day: for each load needed during outages, watts × outage hours, "
                   "summed and divided by 1000."),
    # ---- cable page / PF page -----------------------------------------------------------------
    "cable_len": ("Tape it, one way (m)",
                  "One-way length of the cable route from supply to load, following walls/trays, plus ~10% for bends. "
                  "Enter one way only; the return conductor is included by the formula."),
    "vd_limit": ("e.g. 3 (IEC lighting)",
                 "Allowed voltage drop as % of nominal voltage. IEC 60364 / BS 7671 allow 3% for lighting and 5% for "
                 "other loads for the whole installation (from the supply origin). Use your project specification."),
    "nom_v": ("230 (1-ph) or 400 (3-ph)",
              "Nominal circuit voltage: phase-neutral for single-phase, line-line for three-phase, battery voltage for DC."),
    "design_i": ("Nameplate amps",
                 "Full-load current from the equipment nameplate, or calculate: single-phase I = P ÷ (V × PF), "
                 "three-phase I = P ÷ (1.732 × V × PF)."),
    "pf": ("Motor nameplate cos φ",
           "Power factor of the load: motor nameplate 'cos φ' (often 0.8-0.9); heaters/lights ≈ 1."),
    "reactance": ("Datasheet; blank = 0",
                  "Conductor reactance from the cable datasheet (mΩ/m, often ~0.08). Matters for 35 mm² and above."),
    "max_demand": ("From the bill (kW)",
                   "Sizing basis for the capacitor bank: the maximum demand (kW) shown on the industrial bill or "
                   "measured with a power analyser. Not the average."),
    "kwh": ("From bill / meter", "Active energy for the billing period from the bill or the meter's kWh register."),
    "kvarh": ("From bill / meter",
              "Reactive energy for the same period from the bill or the meter's kVArh register."),
    "pf_existing": ("From bill, e.g. 0.72",
                    "Average power factor from the bill or measured with a power analyser / PF meter."),
    "pf_target": ("Often 0.95",
                  "The power factor you want to reach. Check the utility's minimum PF requirement for the tariff "
                  "category; 0.95 is a common target."),
    "pf_volts": ("e.g. 400", "Line-to-line voltage at the capacitor bank, for µF per phase."),
}


def num(container, key: str, label: str, lo: float = 0.0, hi: float = 1e9, step: float | None = None,
        disabled: bool = False, wkey: str | None = None):
    """Empty number box with a how-to placeholder and help tooltip. Returns None while empty."""
    ph, hp = H[key]
    return container.number_input(label, min_value=lo, max_value=hi, value=None, step=step, placeholder=ph,
                                  help=hp, disabled=disabled, key=wkey or f"in_{key}_{label}")


def missing(fields: dict[str, object]) -> list[str]:
    return [name for name, v in fields.items() if v is None or (isinstance(v, str) and not v.strip())]
