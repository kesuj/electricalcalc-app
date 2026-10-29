"""Findings of the Oct 2026 deep research (reports/Nepal solar PV component guide.md) added to the component
cards. Each addition names its source. Applied after ecalc.guide.component_guide builds the cards."""

from __future__ import annotations

SRC_NEPQA = "NEPQA-2025 (AEPC, Aug 2025) and Amendment-1 (Apr 2026)"
SRC_AEPC_EARTH = "AEPC 2 kWp institutional PV bidding specification (earthing clause)"
SRC_PYLON = "Pylontech US5000 operation manual (2024)"
SRC_NEA = "NEA Board decision (776th meeting, 2018) - latest verifiable grid-connection rules"


def _add(card: dict, key: str, items: list[str]) -> None:
    card.setdefault(key, [])
    card[key] = list(card[key]) + [i for i in items if i not in card[key]]


def apply_research(cards: list[dict], pkg, x, ii) -> list[dict]:
    t_min = (pkg.strings or {}).get("t_min_c")
    pv_run = getattr(ii, "len_array_to_inverter_m", 0) or 0
    for c in cards:
        n = c["name"].lower()
        if n.startswith("solar panels"):
            _add(c, "buying_checklist", [
                f"Certificates from an IECEE/IECRE-listed lab: IEC 61215:2021 and IEC 61730; above 350 W also PID "
                f"(IEC 62804-1), salt-mist (IEC 61701) and ammonia (IEC 62716) - {SRC_NEPQA}.",
                f"Serial number laminated INSIDE the glass (a sticker only is a warning sign); fill factor ≥ 75 % - {SRC_NEPQA}.",
                "Power warranty ≥ 97 % in year 1, ≥ 90 % at 10 years, ≥ 80 % at 25 years (≤ 0.8 %/yr) - NEPQA-2025."])
            _add(c, "how_to_connect", [
                "Leave about 10 mm between neighbouring panels and at least 10 cm between the panel frame and the roof "
                "for cooling (manufacturer manual, e.g. LONGi 2026).",
                "Bond each frame to earth through the marked earthing hole with the proper star washer/lug - never drill "
                "new holes in the frame (manufacturer manual)."])
        elif "charge controller" in n:
            _add(c, "how_to_select", [
                f"NEPQA-2025 allows PWM controllers only below 20 A; above that use MPPT (efficiency ≥ 95 %, PWM ≥ 90 %) - {SRC_NEPQA}.",
                "Keep the coldest-morning string Voc at or below about 95 % of the controller's maximum PV voltage."])
        elif "surge protector" in n and "dc" in n:
            extra = ([f"Your panel-to-inverter cable is {pv_run:g} m: because it is 10 m or more, fit a SECOND DC SPD in "
                      "a box near the panels as well as the one at the inverter (IEC 61643-32 practice)."]
                     if pv_run >= 10 else
                     ["Your panel-to-inverter cable is under 10 m, so one DC SPD at the inverter end is enough."])
            _add(c, "how_to_select", extra + [
                "Nepal recorded 237 lightning deaths in 2021-2025 (Koshi and Lumbini worst) - do not skip surge protection."])
        elif n.startswith("inverter"):
            _add(c, "buying_checklist", [
                f"Grid-tied: test certificates IEC 61727, IEC 62116 (anti-islanding), IEC 62109-1/-2 (+ IEC 61683, "
                f"IEC 61000 EMC per Amendment-1); efficiency ≥ 95 % (≤ 5 kVA) / ≥ 97 % above; IP65; built-in meter and "
                f"data logger; warranty ≥ 5 years - {SRC_NEPQA}.",
                f"Battery/hybrid inverters: efficiency ≥ 90 % (transformerless), must survive 150 % load for 2 s, hybrid "
                f"must charge from solar first; warranty ≥ 3 years up to 5 kVA - {SRC_NEPQA}."])
            if x.mode in ("grid_tied", "hybrid_backup"):
                _add(c, "how_to_select", [f"NEA connection voltage: up to 5 kW single-phase 230 V; 5-40 kW three-phase "
                                          f"400 V; above 40 kW at 11 kV - {SRC_NEA}."])
        elif n.startswith("battery bank"):
            sel = [f"Lithium (LiFePO4) must only be CHARGED between about 0 °C and 50 °C (some makers say 5 °C) - "
                   f"charging below freezing permanently damages it ({SRC_PYLON}; Victron).",
                   f"Never connect 48 V lithium modules in SERIES - only in parallel, and at most the number the maker "
                   f"allows per group ({SRC_PYLON}).",
                   "Before joining modules in parallel, bring them to the same voltage (charge each fully) and let them "
                   "rest at least 15 minutes."]
            if t_min is not None and t_min < 5:
                sel.insert(0, f"Your site can reach {t_min:g} °C: keep a lithium battery INDOORS in a room that stays "
                              "above 5 °C, or choose a battery with self-heating; otherwise it must not charge on cold mornings.")
            _add(c, "how_to_select", sel)
            _add(c, "buying_checklist", [
                f"NEPQA-2025: lithium ≥ 3000 cycles at 80 % DoD (≥ 2000 below 2 kWh), BMS with cell protection, "
                f"round-trip efficiency ≥ 85 %, warranty ≥ 5 years; 12 V lead-acid ≥ 1200 cycles, warranty ≥ 3 years; "
                f"test reports IEC 62619 / IEC 61427 / IEC 60896 - {SRC_NEPQA}.",
                "Measured capacity must be 0 to +20 % of the label, never less (NEPQA-2025) - ask the seller to show a "
                "discharge test or check it yourself in the first weeks via the inverter's energy counter."])
        elif "battery cables" in n:
            _add(c, "how_to_select", [
                f"A 48 V lithium module can push about 2,500 A into a short circuit: the battery fuse/breaker must be "
                f"DC-rated with a breaking capacity of at least 10 kA (1-4 modules) or 20 kA (5-8 modules) - "
                f"{SRC_PYLON}. Class T fuses (20 kA) meet this; small automotive-style fuses do not."])
        elif n.startswith("earthing"):
            _add(c, "how_to_select", [
                f"AEPC's own specification: at least TWO earth electrodes (pipe-in-pipe or copper-bonded rod) each "
                f"≥ 2.5 m long, 2.5 m apart, each with ~30 kg earth-enhancing compound and a concrete inspection pit; "
                f"bonding conductors 6 mm² (frames) / 16 mm² copper; electrodes linked with 50 mm² bare copper buried "
                f"0.5 m deep - {SRC_AEPC_EARTH}.",
                f"Target earth resistance 10 Ω or less (AEPC PV spec); lightning-protection earths are often required "
                f"≤ 5 Ω - {SRC_AEPC_EARTH}.",
                "Hill sites in Nepal measured 39-226 Ω before improvement (AEPC Dhading tender): always measure, and add "
                "electrodes or compound until the target is met."])
        elif "nea" in n and "meter" in n:
            _add(c, "how_to_select", [
                f"Minimum system for NEA grid connection was 500 W; households 0.5-10 kW (2018 rules) - {SRC_NEA}.",
                "Export is credited at about Rs 5.94/kWh (net billing since July 2022) while you pay up to Rs 11/unit "
                "for imports - so size the system to USE most of your solar yourself."])
    return cards


def legal_points_2026(x) -> list[str]:
    """Corrected legal stop-points (research Oct 2026: no statutory house-wiring licence was found in Nepal)."""
    pts = [
        "House wiring (230 V AC): no Nepali law requiring a licensed electrician for house or solar wiring was found "
        "(only CTEVT/NSTB skill certificates exist). You may do it yourself if you follow this report exactly and "
        "test the RCD and earth afterwards - but 230 V AC can kill: if you are not confident, have a CTEVT-certified "
        "electrician do the AC connection while you watch, and check their work against this report.",
        "Everything on the DC side (panels, mounting, DC cables, isolator, SPD"
        + (", battery" if x.mode != "grid_tied" else "") + ") can be done by a careful owner following this report, "
        "but panels are live whenever light falls on them - cover them while wiring.",
    ]
    if x.mode in ("grid_tied", "hybrid_backup"):
        pts.append("COMPULSORY: apply to your NEA distribution centre before connecting to or exporting to the grid. "
                   "NEA approves the system and fits/seals the bidirectional meter. Export without approval is not allowed "
                   "and endangers line workers during outages. Keep export switched OFF until approved. The procedure's "
                   "validity after mid-2025 was unclear - confirm the current steps at your NEA office.")
    if x.mode == "hybrid_backup":
        pts.append("Never connect the inverter's backup output and the NEA supply together - the changeover must be "
                   "break-before-make.")
    pts.append("If anything gets hot, smells of burning, or the display shows an earth/insulation fault: switch off in "
               "the shutdown order and do not restart until the cause is found.")
    return pts
