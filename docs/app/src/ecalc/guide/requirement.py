"""Is each shopping-list item compulsory or optional in Nepal? (research Oct 2026; same table as the
'Nepal Solar PV Component Guide 2026' document). Levels:
  Compulsory (law/NEA) - NEPQA-2025, NEA rules;  Compulsory (safety) - IEC safety standards / AEPC specs;
  Strongly recommended - real Nepal risk;  Optional - convenience.
"""

from __future__ import annotations

LAW, SAFETY, RECOMMENDED, OPTIONAL = "Compulsory (law / NEA)", "Compulsory (safety)", "Strongly recommended", "Optional"

# (keyword in item name, level, reason) - first match wins
RULES: list[tuple[str, str, str]] = [
    ("nea", LAW, "NEA must approve and fit/seal the meter before you connect or export"),
    ("bidirectional", LAW, "NEA must approve and fit/seal the meter before you connect or export"),
    ("mc4", LAW, "NEPQA-2025: connector of the panel maker's type, IEC 62852, IP67"),
    ("connector", LAW, "NEPQA-2025: connector of the panel maker's type, IEC 62852, IP67"),
    ("string fuse", SAFETY, "Needed because 3 or more strings are joined in parallel (IEC 62548)"),
    ("surge", RECOMMENDED, "Nepal lightning risk (237 deaths 2021-2025); AEPC specs include SPDs"),
    ("spd", RECOMMENDED, "Nepal lightning risk (237 deaths 2021-2025); AEPC specs include SPDs"),
    ("lightning", OPTIONAL, "Only for exposed hilltop or tall buildings (IEC 62305 risk check)"),
    ("monitor", OPTIONAL, "Useful to spot faults; grid inverters already include a logger (NEPQA)"),
    ("wi-fi", OPTIONAL, "Useful to spot faults; grid inverters already include a logger (NEPQA)"),
    ("export limit", OPTIONAL, "Only if you must not export before NEA approval"),
    ("ct ", OPTIONAL, "Only if you must not export before NEA approval"),
    ("clean", OPTIONAL, "Keeps output up"),
    ("spare", OPTIONAL, "Quick repairs"),
    ("label", SAFETY, "IEC 62548: warn that DC is live in daylight"),
    ("rcd", SAFETY, "Prevents electric shock (IEC 60364)"),
    ("rcbo", SAFETY, "Prevents electric shock (IEC 60364)"),
    ("mcb", SAFETY, "Protects the AC cable (IEC 60364)"),
    ("breaker", SAFETY, "Protects the cable it feeds"),
    ("battery isolator", SAFETY, "Safe disconnection of the battery"),
    ("inverter", LAW, "NEPQA-2025 certificates (IEC 61727/62116/62109); NEA anti-islanding"),
    ("bms", LAW, "NEPQA-2025: lithium batteries must have a BMS"),
    ("battery fuse", SAFETY, "A lithium bank can push thousands of amps into a short"),
    ("battery isolator", SAFETY, "Safe disconnection of the battery"),
    ("battery cable", SAFETY, "Must carry the fuse rating and inverter current"),
    ("battery", SAFETY, "Stores the backup energy; NEPQA-2025 cycle, capacity and warranty floors"),
    ("charge controller", SAFETY, "Charges the battery; NEPQA: PWM only below 20 A, MPPT >= 95 %"),
    ("changeover", SAFETY, "Break-before-make: backup power must never feed the dead NEA line"),
    ("backup", SAFETY, "Separate board for power-cut circuits"),
    ("isolator", SAFETY, "Safe disconnection of panel power (IEC 60364-7-712)"),
    ("earth", SAFETY, "AEPC spec: 2 electrodes, 10 ohm or less"),
    ("cable", SAFETY, "Solar-rated (EN 50618) or correctly sized copper"),
    ("conduit", SAFETY, "Protects cables from sun, rodents and damage"),
    ("gland", SAFETY, "Keeps water and dust out of enclosures"),
    ("module", SAFETY, "IEC 61215/61730; NEPQA-2025 efficiency and warranty floors"),
    ("panel", SAFETY, "IEC 61215/61730; NEPQA-2025 efficiency and warranty floors"),
    ("mount", SAFETY, "Must resist wind uplift and earthquakes"),
    ("rail", SAFETY, "Part of the mounting structure"),
    ("clamp", SAFETY, "Part of the mounting structure"),
    ("roof", SAFETY, "Part of the mounting structure"),
    ("multimeter", SAFETY, "Needed for the commissioning tests (IEC 62446)"),
    ("tool", SAFETY, "Needed to install and test safely"),
]


def classify(item: str, mode: str = "grid_tied") -> tuple[str, str]:
    name = item.lower()
    for key, level, why in RULES:
        if key in name:
            if key in ("nea", "bidirectional") and mode == "off_grid":
                return OPTIONAL, "Off-grid: no NEA connection"
            if key == "inverter" and (mode == "off_grid" or "off-grid" in name):
                return SAFETY, "Battery inverter: NEPQA-2025 efficiency, overload and warranty floors"
            return level, why
    return RECOMMENDED, "Check the reason in the component card"


def with_requirement(bom: list[dict], mode: str) -> list[dict]:
    """Shopping list with a 'Compulsory or optional?' column right after the item name."""
    out = []
    for r in bom:
        level, why = classify(str(r.get("Item", "")), mode)
        row = {"Item": r.get("Item"), "Compulsory or optional?": level}
        row.update({k: v for k, v in r.items() if k != "Item"})
        row["Why it is needed"] = why
        out.append(row)
    return out


def requirement_table(mode: str) -> list[dict]:
    """Summary rows for the report, for the chosen system type."""
    mode_name = {"grid_tied": "Grid-tied", "hybrid_backup": "Hybrid (backup)", "off_grid": "Off-grid"}[mode]
    rows = [
        ("Solar panels (IEC 61215 + 61730)", SAFETY), ("Mounting structure, anchored", SAFETY),
        ("Solar DC cable (EN 50618)", SAFETY), ("MC4 connectors of the panel maker's type", LAW),
        ("DC isolator", SAFETY), ("DC surge protector", RECOMMENDED),
        ("Inverter with NEPQA/IEC certificates", LAW if mode != "off_grid" else SAFETY),
        ("AC breaker (MCB)", SAFETY), ("RCD 30 mA", SAFETY), ("AC surge protector", RECOMMENDED),
        ("Earthing (2 electrodes, <= 10 ohm)", SAFETY), ("Warning labels", SAFETY),
        ("Multimeter for testing", SAFETY), ("Lightning air terminal", OPTIONAL), ("Monitoring app", OPTIONAL),
    ]
    if mode in ("hybrid_backup", "off_grid"):
        rows += [("Battery with BMS (lithium)", LAW), ("Battery fuse (10-20 kA) + isolator", SAFETY)]
    if mode == "off_grid":
        rows += [("MPPT charge controller (PWM only below 20 A)", LAW)]
    if mode == "hybrid_backup":
        rows += [("Changeover switch + backup board", SAFETY)]
    if mode in ("grid_tied", "hybrid_backup"):
        rows += [("NEA approval + bidirectional meter", LAW), ("Export limiter", OPTIONAL)]
    order = {LAW: 0, SAFETY: 1, RECOMMENDED: 2, OPTIONAL: 3}
    rows.sort(key=lambda r: order[r[1]])
    return [{"Part": p, f"{mode_name}": lvl} for p, lvl in rows]
