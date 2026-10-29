"""One card per component: what it is, the types, which is best for THIS system, how to select it with the
user's own numbers, what to check when buying, series/parallel, how to connect it and common mistakes.

Sources: Boxwell, *Solar Electricity Handbook* (2012) chapters on components (§74-§96), detailed design
(§104-§112), installation (§117-§130) and maintenance (§131-§139) - paraphrased; "[modern]" marks practice
that post-dates the book (LiFePO4, TOPCon panels, hybrid inverters, NEPQA-2025). No brands are recommended.
"""

from __future__ import annotations


MODES = ("grid_tied", "hybrid_backup", "off_grid")
NEPQA_NOTE = "any brand listed/certified under NEPQA-2025 (AEPC); always ask the seller for the datasheet"


# ---- helpers to read the user's numbers from the package -------------------------------------------------
def _bom(pkg, prefix: str) -> dict | None:
    return next((b for b in pkg.bom if b["Item"].lower().startswith(prefix.lower())), None)


def _spec(pkg, prefix: str, default: str = "see shopping list") -> str:
    b = _bom(pkg, prefix)
    return b["Specification"] if b else default


def _qty(pkg, prefix: str, default="-"):
    b = _bom(pkg, prefix)
    return b["Qty"] if b else default


def _cable(pkg, prefix: str) -> dict | None:
    return next((c for c in pkg.cable_schedule if c["Circuit"].lower().startswith(prefix.lower())), None)


def _out(design, key, default=None):
    q = design.outputs.get(key)
    return q.value if q is not None else default


def _n(v, d: int = 0) -> str:
    if isinstance(v, (int, float)):
        return f"{v:,.{d}f}"
    return str(v)


def _ctx(pkg, design, x, ii) -> dict:
    s = pkg.strings or {}
    v_sys = _out(design, "system_v")
    bat_c = _cable(pkg, "Battery cable")
    pv_c = _cable(pkg, "PV string")
    ac_c = _cable(pkg, "Inverter AC")
    module_v = ii.battery_module_v or v_sys
    module_ah = ii.battery_module_ah or (100 if str(x.chemistry).startswith("LiFePO4") else 150)
    return {
        "mode": x.mode, "panels": s.get("panels", _out(design, "panel_count")), "wp": x.panel_wp,
        "ns": s.get("modules_per_string"), "np": s.get("strings"), "kwp": s.get("kwp"),
        "voc": ii.voc, "vmp": ii.vmp, "isc": ii.isc, "imp": ii.imp, "beta": ii.beta_voc_pct,
        "voc_cold": s.get("string_voc_cold_v"), "voc_stc": s.get("string_voc_stc_v"),
        "vmp_stc": s.get("string_vmp_stc_v"), "vmp_hot": s.get("string_vmp_hot_v"),
        "tmin": s.get("t_min_c"), "tmax": s.get("t_max_c"), "pv_input": s.get("pv_input", "inverter"),
        "pv_limits": s.get("pv_input_limits", ""), "string_fuse": s.get("string_fuses"),
        "v_sys": v_sys, "bs": s.get("battery_series"), "bp": s.get("battery_parallel"),
        "bat_kwh": s.get("battery_kwh"), "module_v": module_v, "module_ah": module_ah,
        "chem": x.chemistry, "dod": _out(design, "dod") or (design.inputs["dod"].value if "dod" in design.inputs else None),
        "inv_w": _out(design, "inverter_w"), "peak_w": _out(design, "peak_w"),
        "bat_ah_needed": _out(design, "battery_ah"), "bat_usable_wh": _out(design, "battery_usable_wh"),
        "ctrl_a": _out(design, "controller_a"), "area": _out(design, "array_area_m2"),
        "bat_cable": bat_c, "pv_cable": pv_c, "ac_cable": ac_c, "roof": ii.roof, "inv_loc": ii.inverter_location,
        "isc_string": round(1.25 * ii.isc, 1), "max_fuse": ii.module_max_fuse_a,
    }


def _card(name, what, types, best, select, buying, sp, connect, mistakes, ref) -> dict:
    return {"name": name, "what_it_does": what, "types": types, "best_for_you": best, "how_to_select": select,
            "buying_checklist": buying, "series_or_parallel": sp, "how_to_connect": connect, "mistakes": mistakes,
            "ref": ref}


# ---- cards -----------------------------------------------------------------------------------------------
def _panels(c, pkg):
    sp = (f"Your {c['panels']} panels are wired as {c['ns']} in series × {c['np']} string(s). In series the VOLTAGES "
          f"add and the current stays the same: {c['ns']} × {_n(c['vmp'], 1)} V = about {_n(c['vmp_stc'])} V while "
          f"working, {_n(c['voc_stc'])} V open-circuit on a 25 °C test, and up to {_n(c['voc_cold'])} V on the coldest "
          f"morning ({_n(c['tmin'], 1)} °C). The current is that of one panel, about {_n(c['imp'], 1)} A working / "
          f"{_n(c['isc'], 1)} A short-circuit." +
          (f" The {c['np']} strings join in parallel, so their CURRENTS add (about {_n(c['imp'] * c['np'], 1)} A) and "
           "the voltage stays the same." if (c["np"] or 1) > 1 else ""))
    return _card(
        "Solar panels (PV modules)",
        "Panels turn sunlight into DC electricity. Their power rating (Wp) is measured in a laboratory at 25 °C and "
        "full sun, so on a real roof they give less - that loss is already included in your design.",
        [{"Type": "Monocrystalline TOPCon / PERC [modern]", "How it works": "Single-crystal silicon cells, black look",
          "Good": "Highest efficiency (21-23 %), small roof area, long life", "Bad": "Slightly dearer per watt",
          "Best for": "Almost every Nepali roof today"},
         {"Type": "Bifacial", "How it works": "Glass on both sides collects reflected light too",
          "Good": "A few % extra on a bright raised frame", "Bad": "Little gain flat on a tin roof; heavier",
          "Best for": "Ground or high open frames over light-coloured surfaces"},
         {"Type": "Polycrystalline", "How it works": "Many-crystal cells, blue look (book §76)",
          "Good": "Cheap", "Bad": "Lower efficiency (13-18 %), mostly discontinued; fails NEPQA ≥ 21 % above 350 Wp",
          "Best for": "Small old-stock DC lighting kits only"},
         {"Type": "Thin-film / amorphous", "How it works": "Very thin layer on glass (book §76)",
          "Good": "Copes better with partial shade and heat", "Bad": "Needs about 2.5× more roof area",
          "Best for": "Rarely sold in Nepal now"}],
        f"Monocrystalline (TOPCon/PERC) panels of about {_n(c['wp'])} W - you need {c['panels']} of them "
        f"(about {_n(c['area'])} m² of roof). Buy all panels of the SAME model and batch.",
        [f"Power about {_n(c['wp'])} Wp each, quantity {c['panels']} (your design).",
         f"Datasheet values close to: Voc {_n(c['voc'], 1)} V, Vmp {_n(c['vmp'], 1)} V, Isc {_n(c['isc'], 1)} A, "
         f"Imp {_n(c['imp'], 1)} A - if your panel differs, re-enter its values in Engineer settings and recalculate.",
         f"Voc temperature coefficient around {_n(c['beta'], 2)} %/°C (smaller number = less voltage rise in cold).",
         "Maximum system voltage 1000 V or 1500 V (higher than your string's cold voltage).",
         "Efficiency at least 21 % for panels above 350 Wp (NEPQA-2025)."],
        ["Label on the back: model, Wp, Voc, Isc, Vmp, Imp, max system voltage, max series fuse, certificates "
         "IEC 61215 and IEC 61730.",
         "Power tolerance 0/+3 % or 0/+5 W (never a minus tolerance) - NEPQA-2025.",
         "Warranty: product ≥ 10 years; power ≥ 80 % after 25 years (NEPQA floor).",
         f"Buy from {NEPQA_NOTE}.",
         "Signs of a poor/fake panel: weight much lighter than the datasheet, no serial number, bubbles or brown "
         "spots in the cells, bent frame, a junction box that opens easily, 'Wp' far too high for its size.",
         "Ask the shop to measure Voc in the sun in front of you - it should be close to the label value."],
        sp,
        ["Keep panels face-down or covered with an opaque sheet until all wiring is finished - a panel in daylight is "
         "always live (book §117-§120).",
         "Fix each panel to the rails with 4 clamps on the frame's clamping zone shown in the manual.",
         f"Join the panels in a chain: + of panel 1 to − of panel 2, and so on, for {c['ns']} panels. The free − of "
         "the first panel and the free + of the last panel are the string ends.",
         "Measure the string's open-circuit voltage with a multimeter before connecting it anywhere (see Skills).",
         "Bond every panel frame / rail to earth with 6 mm² green-yellow cable."],
        ["Mixing different panel models or wattages in one string (the weakest one limits all).",
         "Wiring in the shade of a water tank, railing or neighbour's building - even small shade cuts output a lot "
         "(book §57: 5 % shaded can lose 50-80 %).",
         "Walking or standing on panels; drilling the frame.",
         "Leaving the panel's own short leads hanging in water - tie them to the rail."],
        "Book §56-§61, §76, §106, §117-§120; NEPQA-2025 §1.1")


def _mounting(c, pkg):
    rcc = str(c["roof"]).startswith("RCC")
    return _card(
        "Mounting structure (frame, rails, clamps)",
        "The frame holds the panels at the right angle and must survive Nepal's monsoon storms for 25 years. "
        "It also lifts the panels so air can cool them.",
        [{"Type": "Raised tilted frame on a flat RCC roof", "How it works": "Galvanised/aluminium legs bolted to the slab",
          "Good": "Correct tilt and direction, cooler panels", "Bad": "Must be anchored for wind", "Best for": "Flat roofs"},
         {"Type": "Rails on a tin / sloping roof", "How it works": "Rails fixed through the sheet into the purlins",
          "Good": "Cheap, quick", "Bad": "Follows roof angle; leaks if badly sealed", "Best for": "Tin or tiled roofs"},
         {"Type": "Ground frame / pole", "How it works": "Concrete footings in the yard (book §66)",
          "Good": "Easy cleaning, any angle", "Bad": "Uses land; needs fencing from animals/children",
          "Best for": "Houses with yard space"}],
        ("A hot-dip galvanised or aluminium tilted frame bolted to your RCC slab with anchor bolts and sealed."
         if rcc else "Aluminium rails screwed into the roof purlins (not just the sheet) with sealed roof feet."),
        [f"Size: holds {c['panels']} panels (shopping list: {_spec(pkg, 'Mounting structure')}).",
         f"Rails: {_qty(pkg, 'Mounting rails')}; clamps: {_qty(pkg, 'End clamps')}; roof feet/anchors: "
         f"{_qty(pkg, 'Roof feet')}.",
         "Leave at least 10 cm of air under the panels (book §59: hot panels make less power).",
         "Face the panels south; tilt as in your design (flat roofs: about equal to your latitude)."],
        ["Steel must be hot-dip GALVANISED (dull grey, thick zinc) - not painted mild steel which rusts in 2-3 monsoons.",
         "Stainless steel (A2) bolts and clamps; matching the panel frame thickness (e.g. 30-35 mm).",
         "Ask for the wind rating of the frame and follow its anchor spacing."],
        None,
        (["Mark the frame positions on the slab; keep 30-50 cm from roof edges and away from the water tank's shadow.",
          "Drill the slab, set anchor bolts with chemical/epoxy anchor or expansion bolts, and seal around each one.",
          "Bolt the legs, check the tilt with a phone angle app, then fix the rails level."] if rcc else
         ["Find the purlins (the steel/wood beams under the sheet) - screw roof feet into them, never into sheet only.",
          "Put rubber EPDM washers and roofing sealant at every hole.", "Fix rails across the feet and check they are straight."]) +
        ["Tighten all bolts to the torque in the manual; re-check after the first storm (book §135)."],
        ["Fixing into the tin sheet only - it tears in wind.", "No sealing → roof leaks inside the house.",
         "Rusting black steel frames.", "Panels too close to the roof surface (overheating)."],
        "Book §59, §66, §123; local building rules for roof loads")


def _pv_cable(c, pkg):
    pc = c["pv_cable"] or {}
    return _card(
        "PV cable and MC4 connectors",
        "Special solar cable carries the DC power from the panels to the inverter/controller. MC4 connectors are "
        "the waterproof plugs used to join panels and cables.",
        [{"Type": "Solar cable EN 50618 (H1Z2Z2-K)", "How it works": "Double-insulated, UV- and heat-proof, rated 1500 V DC",
          "Good": "Lasts 25 years outdoors", "Bad": "Dearer than house wire", "Best for": "All panel wiring"},
         {"Type": "Ordinary PVC house wire", "How it works": "Single insulation, not UV proof",
          "Good": "Cheap", "Bad": "Cracks in sun within a few years → fire/shock risk", "Best for": "Never for PV"}],
        f"{_spec(pkg, 'PV cable')}, {pc.get('Chosen (mm²)', '-')} mm², red for + and black for −, "
        f"{_qty(pkg, 'PV cable')}; {_qty(pkg, 'MC4')} MC4 pairs of the same make as the panel plugs.",
        [f"Size {pc.get('Chosen (mm²)', '-')} mm² (larger of: current rule {pc.get('Size for current (mm²)', '-')} mm², "
         f"voltage-drop rule {pc.get('Size for voltage drop (mm²)', '-')} mm²); voltage drop about "
         f"{pc.get('Voltage drop (%)', '-')} % over {pc.get('Length (m)', '-')} m.",
         f"Voltage rating ≥ {_n(c['voc_cold'])} V DC (your coldest-morning string voltage) - EN 50618 cable is 1500 V.",
         f"Current: each string carries up to {c['isc_string']} A (1.25 × Isc)."],
        ["Print on the cable sheath: 'EN 50618' or 'H1Z2Z2-K', size in mm², 1500 V DC.",
         "Tinned copper strands; correct size (strip a sample - undersized copper is a common fake).",
         "MC4 connectors: IP67/IP68, rated ≥ 30 A and ≥ 1000 V, same make as your panels' connectors.",
         f"Buy from {NEPQA_NOTE}."],
        "Solar cable is not 'in series' or 'in parallel' itself - it simply carries the string. Keep + and − of the "
        "same string together (same route) so they do not form a large loop that picks up lightning surges.",
        ["Route the + and − cables side by side in UV-proof conduit or tied to the rails; never lie them in water.",
         "Crimp MC4 ends with an MC4 crimp tool (see Skills) - never squeeze with pliers.",
         "Check polarity with a multimeter before plugging into the isolator.", "Label both ends: 'PV string 1 +' / '−'."],
        ["Mixing MC4 brands (they look the same but can overheat and melt).", "Using house wire on the roof.",
         "Sharp bends over metal edges cutting the insulation.", "Cables dangling and rubbing in the wind."],
        "Book §87, §110; EN 50618; IEC 62548")


def _string_fuse(c, pkg):
    f = c["string_fuse"]
    return _card(
        "PV string fuses",
        "When three or more strings are joined in parallel, a fault in one string can pull the current of all the "
        "others backwards through it. A string fuse stops that.",
        [{"Type": "gPV DC fuse in a fused combiner box", "How it works": "Fuse made for solar DC (gPV)",
          "Good": "Correct for PV", "Bad": "Needs a combiner box", "Best for": "3 or more strings in parallel"}],
        f"gPV fuses of {f} A on both + and − of each string." if f else
        "Your system does not need string fuses (fewer than 3 strings in parallel or the panel can take the reverse current).",
        [f"Rating {f} A: between 1.5 × Isc ({_n(1.5 * c['isc'], 1)} A) and 2.4 × Isc ({_n(2.4 * c['isc'], 1)} A) and not "
         f"above the panel's 'max series fuse' ({_n(c['max_fuse'])} A)." if f else "Not required for your design.",
         f"Voltage ≥ {_n(c['voc_cold'])} V DC."],
        ["Fuse must be marked gPV and the DC voltage (e.g. 1000 V DC).", "Holder rated for DC."],
        None,
        ["Fit fuses in the combiner box only after all strings are tested; open the DC isolator first."],
        ["Using AC fuses for DC.", "Fusing only one pole on a floating system."],
        "IEC 62548 (string overcurrent); book §109")


def _dc_isolator(c, pkg):
    return _card(
        "DC isolator / DC breaker (panel side)",
        "A switch that safely disconnects the panels from the inverter or controller, so you can work on the system. "
        "DC is harder to switch off than AC - it makes a lasting spark - so the switch must be DC-rated.",
        [{"Type": "DC isolator (rotary switch)", "How it works": "Manual switch rated for DC voltage",
          "Good": "Simple, lockable, cheap", "Bad": "No automatic overcurrent trip", "Best for": "Disconnect at the inverter"},
         {"Type": "DC MCB (breaker)", "How it works": "Switch + automatic trip on overcurrent",
          "Good": "Protects as well as isolates", "Bad": "Must be polarity-correct; dearer", "Best for": "Small PV/battery circuits"},
         {"Type": "AC MCB used on DC", "How it works": "Wrong device", "Good": "-",
          "Bad": "Can fail to break DC → fire", "Best for": "Never"}],
        f"{_spec(pkg, 'DC isolator')} - qty {_qty(pkg, 'DC isolator')} (one near the inverter; a second at the array "
        "if the cable run is long or crosses the roof).",
        [f"Voltage rating ≥ {_n(c['voc_cold'])} V DC (string voltage on the coldest morning).",
         f"Current rating ≥ {c['isc_string']} A × number of strings ({c['np']}).",
         "2-pole (breaks + and −), lockable in the OFF position."],
        ["'DC' and the voltage (e.g. 600 V DC / 1000 V DC) printed on the device - not just '230/400 V'.",
         "Utilisation category DC-PV2 / DC-21B on the datasheet; IEC 60947-3.", f"Buy from {NEPQA_NOTE}."],
        None,
        ["Mount within reach of the inverter, before its PV input.",
         "Panels + to the isolator's '+ IN', isolator '+ OUT' to the inverter PV +; same for −. Follow the terminal "
         "markings - many DC devices are polarity-sensitive.", "Keep it OFF until commissioning tests are done."],
        ["Using an AC breaker on the PV side.", "Swapping + and − on a polarity-marked DC breaker.",
         "Opening a DC connector (MC4) under load instead of using the isolator (dangerous arc)."],
        "Book §79, §80, §109; IEC 60947-3")


def _dc_spd(c, pkg):
    return _card(
        "DC surge protector (SPD)",
        "Nepal has frequent lightning in the pre-monsoon. A surge protector diverts lightning-induced voltage spikes "
        "on the panel cables to earth before they destroy the inverter.",
        [{"Type": "Type 2 PV SPD", "How it works": "Varistors that conduct to earth during a surge",
          "Good": "Protects against induced surges", "Bad": "Wears out after big surges (indicator turns red)",
          "Best for": "All rooftop systems [modern practice]"},
         {"Type": "Type 1+2 SPD", "How it works": "Handles part of a direct strike current",
          "Good": "Needed with a lightning rod on the building", "Bad": "Dearer", "Best for": "Buildings with lightning protection"}],
        f"{_spec(pkg, 'DC surge')}.",
        [f"Ucpv (max continuous PV voltage) ≥ {_n(c['voc_cold'])} V DC.", "In ≥ 20 kA (8/20 µs), with a status window."],
        ["Marked 'PV' or 'DC' with Ucpv; IEC 61643-31.", "Replaceable cartridges with a visual indicator."],
        None,
        ["Connect it after the DC isolator (between isolator and inverter), + and − to the SPD, its earth terminal "
         "to the earth bar with short (< 0.5 m), straight 6 mm² cable.", "Check the window colour every month."],
        ["Long, looped earth lead (makes the SPD useless).", "Using an AC SPD on DC."],
        "IEC 61643-31; IEC 60364-7-712 [modern]")


def _controller(c, pkg):
    return _card(
        "Charge controller (MPPT)",
        "In an off-grid system the controller sits between the panels and the battery. It charges the battery safely "
        "and stops overcharging. An MPPT type also converts the high panel voltage down to battery voltage without "
        "wasting it.",
        [{"Type": "MPPT", "How it works": "Finds the panel's best working point and converts voltage down",
          "Good": "About 20-30 % more energy than PWM (book §90); allows high-voltage strings and thinner cable",
          "Bad": "Dearer", "Best for": "All systems above about 120 W (book §90)"},
         {"Type": "PWM", "How it works": "Simply connects/disconnects panels to the battery",
          "Good": "Very cheap", "Bad": "Panel voltage must match battery; wastes ~25 % (book §58)",
          "Best for": "Tiny 12 V lighting kits"}],
        f"MPPT controller: {_spec(pkg, 'MPPT charge controller')}.",
        [f"Charge current rating ≥ {_n(c['ctrl_a'])} A (array W ÷ battery V × 1.25).",
         f"Battery voltage {c['v_sys']} V; max PV input voltage ≥ {_n(c['voc_cold'])} V (your cold string Voc) - "
         f"your input limits: {c['pv_limits']}.", "Has a LiFePO4/lithium battery setting (or user-programmable voltages).",
         "Efficiency ≥ 95 % (NEPQA-2025)."],
        ["Datasheet: max PV Voc, max PV current, rated charge current, battery voltages, efficiency.",
         "Real MPPT: has a large heatsink and a stated tracking efficiency; fake 'MPPT' units are often PWM inside "
         "(very light, no input-voltage range above battery voltage).", f"Buy from {NEPQA_NOTE}."],
        None,
        ["ALWAYS connect the BATTERY to the controller first (so it detects the system voltage), then the panels. "
         "Disconnect in the reverse order: panels first, then battery (book §107).",
         "Battery cable from controller to battery busbar through a fuse/breaker (see cable schedule).",
         "Set the battery type/voltages before turning on the panel isolator (see Skills: configure the charger)."],
        ["Connecting panels before the battery (can damage the controller).",
         "PV voltage above the controller's max on a cold morning (destroys it).", "Wrong battery type setting."],
        "Book §58, §90, §107; NEPQA-2025 §1.3")


def _inverter(c, pkg):
    mode = c["mode"]
    item = {"grid_tied": "Grid-tied", "hybrid_backup": "Hybrid inverter", "off_grid": "Off-grid inverter"}[mode]
    spec = _spec(pkg, item)
    best = {"grid_tied": "An on-grid (grid-tied) string inverter",
            "hybrid_backup": "A hybrid inverter with a low-voltage (48/24 V) battery input and a separate backup output",
            "off_grid": "A pure-sine off-grid inverter fed from the battery, with an MPPT controller for the panels"}[mode]
    return _card(
        "Inverter",
        "The inverter turns DC (from panels or battery) into normal 230 V, 50 Hz AC for your appliances. It is the "
        "most important electronic box in the system.",
        [{"Type": "On-grid / grid-tied", "How it works": "Panels → inverter → house and NEA grid; no battery",
          "Good": "Cheapest per kW, most efficient", "Bad": "Switches OFF in power cuts (anti-islanding safety)",
          "Best for": "Lowering the bill where cuts are rare"},
         {"Type": "Hybrid", "How it works": "Panels + battery + grid in one box; backup output for chosen loads",
          "Good": "Saves bill AND gives backup in load-shedding [modern]", "Bad": "Dearer; needs a separate backup DB",
          "Best for": "Most Nepali homes with power cuts"},
         {"Type": "Off-grid (stand-alone)", "How it works": "Battery → inverter → house; panels charge via controller",
          "Good": "Works with no grid at all (book §91)", "Bad": "Battery must cover everything", "Best for": "Remote sites"},
         {"Type": "Modified/square wave", "How it works": "Rough stepped AC (book §91)",
          "Good": "Cheap", "Bad": "Fridges, fans and electronics overheat or hum", "Best for": "Avoid"}],
        f"{best}: {spec}.",
        [f"Continuous power ≥ {_n(c['inv_w'])} W (your design: everything that runs at once × 4/3 rule, and/or the "
         "array size).",
         "Surge (peak) rating at least 2-3× the running power of your largest motor (fridge, pump) - check the "
         "appliance labels (book §91).",
         f"PV input: max voltage above your cold string Voc {_n(c['voc_cold'])} V and MPPT window containing "
         f"{_n(c['vmp_hot'])}-{_n(c['vmp_stc'])} V." if mode != "off_grid" else
         f"DC input {c['v_sys']} V (your battery voltage).",
         "Pure sine wave, 230 V 50 Hz; efficiency ≥ 95 % peak (≤ 5 kVA) / ≥ 97 % (> 5 kVA) per NEPQA-2025."] +
        ([f"Battery voltage {c['v_sys']} V and lithium communication (CAN/RS485) matching your battery."]
         if mode == "hybrid_backup" else []),
        ["Datasheet: continuous W, surge W (and for how many seconds), PV max V, MPPT range, MPPT current, battery V, "
         "efficiency, IP rating (IP65 if outdoors), warranty ≥ 5 years (NEPQA).",
         "For grid-tied/hybrid: anti-islanding certificate (IEC 62116 / IEC 62109) - NEA requires it.",
         "Service centre in Nepal and spare parts; app/Wi-Fi monitoring.", f"Buy from {NEPQA_NOTE}."],
        None,
        ["Mount on a solid wall, indoors and ventilated if possible, out of direct sun, with 30 cm free space around "
         "(book §124).",
         "Connect in this order with everything OFF: earth (PE) first → battery cables (through fuse/isolator) → AC "
         "output to the backup/main DB → PV through the DC isolator." if mode != "grid_tied" else
         "Connect in this order with everything OFF: earth (PE) first → AC output to the DB → PV through the DC isolator.",
         "Tighten terminals to the manual's torque; double-check polarity on DC.",
         "Configure settings (battery type, grid code 230 V/50 Hz) before first start (see Skills)."],
        ["Undersizing the surge rating (fridge/pump won't start).", "Mounting in a hot, closed room or in sun.",
         "Buying a 'modified sine' inverter.", "Grid-tied inverter expected to work in power cuts - it won't."],
        "Book §81-§83, §91, §124; NEPQA-2025 §1.4-§1.5; IEC 62109/62116")


def _battery(c, pkg):
    lead = str(c["chem"]).startswith("Lead")
    sp = (f"Your bank is {c['bs']} module(s) in series × {c['bp']} in parallel of {_n(c['module_v'])} V "
          f"{_n(c['module_ah'])} Ah = {_n(c['v_sys'])} V, about {_n(c['bat_kwh'], 1)} kWh. "
          "In SERIES the voltages add (Ah stays the same): e.g. two 12 V batteries in series = 24 V. "
          "In PARALLEL the Ah add (voltage stays the same). Use identical batteries of the same age and charge level - "
          "a weak one drags the others down and can overheat (book §89, §107).")
    if (c["bp"] or 1) > 1:
        sp += (" For parallel strings take the + lead from the FIRST battery and the − lead from the LAST battery "
               "(diagonal connection) so every battery shares the load equally (book §107).")
    return _card(
        "Battery bank",
        "The battery stores energy for the night and for power cuts. It is the most expensive part to replace, so "
        "choosing and treating it well matters most.",
        [{"Type": "LiFePO4 (lithium iron phosphate) [modern]", "How it works": "Lithium cells + built-in BMS",
          "Good": "Use 80-95 % of capacity, 3,000-6,000+ cycles, light, no topping up", "Bad": "Higher first cost; "
          "must not be charged below 0 °C", "Best for": "Almost all new systems"},
         {"Type": "Tubular lead-acid (flooded)", "How it works": "Liquid acid, tall tubular plates (book §89)",
          "Good": "Cheap, widely repaired", "Bad": "Use only ~50 %; distilled water top-ups; acid fumes; 4-8 years",
          "Best for": "Tight budgets with a ventilated space"},
         {"Type": "AGM / gel (sealed lead-acid)", "How it works": "Sealed, no topping up (book §89)",
          "Good": "No maintenance", "Bad": "Short life when deeply cycled; ~50 % usable", "Best for": "Small loads"}],
        ("LiFePO4 with a built-in BMS, " if not lead else "Tubular lead-acid, ") +
        f"{_spec(pkg, 'Battery')} - quantity {_qty(pkg, 'Battery')}.",
        [f"System voltage {c['v_sys']} V; capacity at least {_n(c['bat_ah_needed'])} Ah at {c['v_sys']} V "
         f"(usable energy needed {_n(c['bat_usable_wh'])} Wh).",
         f"Depth of discharge used in the design: {_n(c['dod'])} %.",
         "Same voltage as the inverter/controller battery input; communication cable (CAN/RS485) compatible with the "
         "inverter for lithium."],
        ["NEPQA-2025 (lithium): ≥ 3,000 cycles at 80 % DoD, round-trip efficiency ≥ 85 %, BMS, warranty ≥ 5 years.",
         "Datasheet: nominal V, Ah, kWh, max charge/discharge current, cycle life at stated DoD, operating temperature.",
         "Signs of poor batteries: weight much lower than datasheet, no cell grade/BMS data, re-labelled cells, no "
         "local warranty service.", f"Buy from {NEPQA_NOTE}."],
        sp,
        ["Place batteries on a stand off the floor, in a cool, dry, ventilated place, away from children (book §125).",
         "Make the series/parallel links with the short cables supplied or equal-length cables of the bank's size.",
         "Connect the bank's + through the battery fuse and isolator to the inverter; − directly (or via isolator).",
         "Cover terminals with insulated caps; keep metal tools away from the top of the battery.",
         "Turn the battery's own switch/BMS on only after all cables are tight."],
        ["Mixing old and new or different-brand batteries.", "Shorting terminals with a spanner (huge current, burns, "
         "explosion risk).", "Thin battery cables (they heat up).",
         "Lead-acid in a closed room (hydrogen gas)." if lead else "Charging lithium below 0 °C (cold Himalayan sites)."],
        "Book §85-§89, §107, §125; NEPQA-2025 §1.2")


def _battery_cable(c, pkg):
    bc = c["bat_cable"] or {}
    return _card(
        "Battery cables, lugs, fuse and isolator",
        "Battery cables carry the largest currents in the system, so they are thick and short. A fuse right next to "
        "the battery protects them from a short circuit; an isolator lets you switch the battery off.",
        [{"Type": "Flexible copper welding/battery cable", "How it works": "Many fine strands", "Good": "Bends easily, "
          "large current", "Bad": "-", "Best for": "Battery links"},
         {"Type": "NH / ANL / class-T DC fuse", "How it works": "High breaking capacity DC fuse",
          "Good": "Safely breaks a battery short circuit", "Bad": "Must be replaced after blowing", "Best for": "Battery +"},
         {"Type": "Automotive blade fuse", "How it works": "Low breaking capacity", "Good": "Cheap",
          "Bad": "Can explode on a battery short", "Best for": "Never on the main battery cable"}],
        f"{bc.get('Chosen (mm²)', '-')} mm² flexible copper, {_spec(pkg, 'Battery fuse')}, {_spec(pkg, 'Battery isolator')}.",
        [f"Cable {bc.get('Chosen (mm²)', '-')} mm² (current rule {bc.get('Size for current (mm²)', '-')} mm², "
         f"voltage-drop rule {bc.get('Size for voltage drop (mm²)', '-')} mm²), length {bc.get('Length (m)', '-')} m "
         f"(keep it short), design current {bc.get('Design current (A)', '-')} A.",
         f"Fuse {bc.get('Protective device (A)', '-')} A DC, high breaking capacity, as close to the battery + as possible.",
         f"Isolator/DC breaker rated ≥ {bc.get('Protective device (A)', '-')} A at {c['v_sys']} V DC."],
        ["Copper (not copper-clad aluminium) - scrape a strand to check colour.", "Lugs sized to the cable AND the "
         "terminal bolt; tinned copper.", "Fuse marked with DC voltage and breaking capacity (kA)."],
        None,
        ["Cut cables to length; crimp lugs with a hydraulic crimper (see Skills); cover with heat-shrink (red +, black −).",
         "Order: battery + → fuse → isolator → inverter/controller +. Battery − → inverter/controller −.",
         "Tighten to the torque in the battery manual; re-check after one week."],
        ["Fuse at the inverter end instead of the battery end.", "Loose lugs (they heat and melt).",
         "Crimping with a hammer."], "Book §87, §109, §110, §125")


def _ac_protection(c, pkg):
    ac = c["ac_cable"] or {}
    return _card(
        "AC breaker (MCB), RCD and AC surge protector",
        "On the 230 V side the MCB protects the cable from overload, the RCD protects people from electric shock, "
        "and the AC surge protector protects appliances from grid and lightning spikes.",
        [{"Type": "MCB (C-curve)", "How it works": "Trips on overload/short", "Good": "Standard", "Bad": "No shock protection",
          "Best for": "Every circuit"},
         {"Type": "RCD 30 mA Type A", "How it works": "Trips if current leaks to earth (through a person)",
          "Good": "Saves lives; works with inverter DC leakage", "Bad": "-", "Best for": "Solar systems [modern]"},
         {"Type": "RCD Type AC", "How it works": "Older type", "Good": "Cheap",
          "Bad": "Can be blinded by DC leakage from inverters", "Best for": "Not recommended with inverters"},
         {"Type": "RCBO", "How it works": "MCB + RCD in one", "Good": "Saves space", "Bad": "Dearer", "Best for": "Backup DB"}],
        f"{_spec(pkg, 'AC MCB')}; {_spec(pkg, 'RCD')}; {_spec(pkg, 'AC surge')}.",
        [f"MCB {ac.get('Protective device (A)', '-')} A for the inverter output (inverter current "
         f"{ac.get('Design current (A)', '-')} A × 1.25, next standard size).",
         f"AC cable {ac.get('Chosen (mm²)', '-')} mm² copper over {ac.get('Length (m)', '-')} m.",
         "RCD 30 mA, Type A (Type B only if the inverter manual says so)."],
        ["IEC 60898 (MCB), IEC 61008/61009 (RCD/RCBO) printed on the device.", "Breaking capacity ≥ 6 kA."],
        None,
        ["Mount in a small DB box next to the inverter or in the backup DB.",
         "Inverter AC output L → MCB → RCD → loads; N through the RCD; PE to the earth bar - never through a breaker.",
         "Press the RCD 'T' test button after switching on: it must trip."],
        ["Putting the RCD before the inverter instead of on its output loads.", "Using Type AC RCDs.",
         "Swapping L and N."], "Book §109; IEC 60364-4-41")


def _changeover(c, pkg):
    return _card(
        "Backup distribution board and changeover switch",
        "A hybrid inverter's backup output feeds only the circuits you chose for power cuts. These circuits move into "
        "a small separate board. A manual bypass/changeover switch lets you feed them from the grid if the inverter "
        "is being serviced.",
        [{"Type": "Separate backup DB", "How it works": "Only the backup circuits are fed by the inverter backup output",
          "Good": "Battery never drains on heavy loads", "Bad": "Some rewiring", "Best for": "Hybrid systems (book §29-§30, §160)"},
         {"Type": "3-position changeover (inverter / off / grid)", "How it works": "Break-before-make switch",
          "Good": "Can never connect two sources together", "Bad": "-", "Best for": "Bypass for maintenance"}],
        f"{_spec(pkg, 'Backup distribution')}; {_spec(pkg, 'Manual bypass')}.",
        ["Move lights, fridge, Wi-Fi, fans (your 'needed in power cut' appliances) to the backup DB.",
         f"Changeover rated ≥ the inverter output MCB ({(c['ac_cable'] or {}).get('Protective device (A)', '-')} A), 2-pole."],
        ["Break-before-make 3-position switch; 2-pole (L and N)."], None,
        ["This is house-wiring work: switch the main switch OFF first; if you are not confident with 230 V, have a CTEVT-certified electrician move the circuits."],
        ["Connecting the inverter output and the grid together (destroys the inverter, dangerous for NEA line workers)."],
        "Book §29-§30, §160")


def _earthing(c, pkg):
    return _card(
        "Earthing (grounding)",
        "Earthing gives fault and lightning currents a safe path into the ground so metal parts never become "
        "dangerous to touch. Every solar system needs it (book §109).",
        [{"Type": "Copper-bonded steel rod", "How it works": "Rod driven 1.5-3 m into moist soil",
          "Good": "Long life, easy to test", "Bad": "Needs depth", "Best for": "Most sites"},
         {"Type": "Plate earth pit (copper/GI plate + charcoal/salt)", "How it works": "Traditional Nepali practice",
          "Good": "Low resistance in dry soil", "Bad": "Salt corrodes; needs watering", "Best for": "Rocky/dry soil"},
         {"Type": "GI pipe", "How it works": "Galvanised pipe in a pit", "Good": "Cheap", "Bad": "Rusts in 5-10 years",
          "Best for": "Temporary"}],
        f"{_spec(pkg, 'Earth electrode')}; cables: {_spec(pkg, 'Earth cable')}.",
        ["PV frames/rails bonded with 6 mm² green-yellow copper; main earth to the electrode 16 mm²; inverter/DB PE "
         "as in the cable schedule.",
         "Bond the PV earth to the house's existing earth (one earthing system for the building)."],
        ["Green-yellow copper cable, bronze/brass clamps, an inspection pit with a removable cover."], None,
        ["Choose moist ground near the building, away from the septic tank.",
         "Drive the rod, fit the clamp, build a small inspection chamber.",
         "Run the 16 mm² cable to the main earth bar; connect PV frame bonding, inverter PE, SPD earths to the bar.",
         "Test the earth resistance (see Skills) and write the value in the commissioning record."],
        ["No earth at all ('the inverter has one inside').", "Earth through a water pipe.",
         "Painted surfaces under earth clamps (no contact)."], "Book §109; IEC 60364-5-54; IEC 62305 (lightning)")


def _lightning(c, pkg):
    return _card(
        "Lightning protection",
        "A lightning rod system is only needed when the building is tall or exposed (hilltop, the tallest roof "
        "around) or already has one. Surge protectors are needed in every case.",
        [{"Type": "Surge protectors only", "How it works": "DC + AC SPDs", "Good": "Cheap, protects electronics",
          "Bad": "Does not protect against a direct strike", "Best for": "Most houses"},
         {"Type": "Lightning rod (air terminal) + down conductor", "How it works": "Intercepts a direct strike",
          "Good": "Protects the building", "Bad": "Must be designed (IEC 62305)", "Best for": "Exposed buildings"}],
        "Surge protectors on DC and AC (already in your list). Add a lightning rod only if your building is exposed - "
        "keep panels at least 0.5-1 m from the rod's down conductor or bond them as its designer specifies.",
        ["If your house has a lightning rod, use Type 1+2 SPDs instead of Type 2."], ["IEC 62305 rated components."],
        None, ["Never run PV cables alongside the lightning down conductor."], ["Assuming SPDs stop direct strikes."],
        "IEC 62305; IEC 61643 [modern]")


def _meter(c, pkg):
    return _card(
        "NEA bidirectional meter and net billing",
        "To export solar power to the NEA grid and get credit, NEA must approve the connection and fit (or approve) "
        "an import/export (bidirectional) meter. This is a legal process, not a purchase.",
        [{"Type": "NEA bidirectional (import/export) meter", "How it works": "Counts units bought and sold separately",
          "Good": "Exports credited (net billing about Rs 5.94/unit, secondary source)", "Bad": "Paperwork and waiting",
          "Best for": "Grid-tied and hybrid systems"}],
        "Apply to your NEA distribution centre before connecting; do not export until approved.",
        ["Ask NEA for the current net-metering/net-billing application form, list of documents, approved inverter "
         "certificates and meter requirements (rules have changed several times - verify current procedure)."],
        ["Inverter anti-islanding certificate (IEC 62116) and datasheet copies ready for NEA.",
         "Single-line diagram from this report."], None,
        ["Submit the application with the inverter certificates and the wiring diagram.",
         "NEA inspects and fits/seals the bidirectional meter; you (or a CTEVT-certified electrician) make the final AC connection only after NEA approval.",
         "Keep the export setting OFF (or zero-export) until approval."],
        ["Exporting before approval (illegal; can be disconnected/fined).", "Assuming the old Rs 7.30 rate."],
        "NEA / ERC procedures (verify current); book §46, §81-§83")


def _monitoring(c, pkg):
    return _card(
        "Monitoring (Wi-Fi dongle / app)",
        "Most modern inverters send their data to a phone app. You see daily energy, battery charge and any fault "
        "codes, so you catch problems early.",
        [{"Type": "Wi-Fi/LAN data logger", "How it works": "Plugs into the inverter's COM port", "Good": "Phone app, alerts",
          "Bad": "Needs Wi-Fi at the inverter", "Best for": "Every system [modern]"},
         {"Type": "Inverter display only", "How it works": "LCD on the unit", "Good": "Free", "Bad": "No history", "Best for": "Off-grid sites"}],
        "Buy the inverter maker's own logger (Wi-Fi) and register the system in its app on day one.",
        ["Make sure Wi-Fi reaches the inverter location."], ["Logger model listed for your inverter model."], None,
        ["Plug the logger in, connect it to home Wi-Fi from the app, check readings match the inverter display."],
        ["Never checking the app - most failures show there first."], "[modern]")


def _tools(c, pkg):
    return _card(
        "Tools and safety gear",
        "Having the right tools makes the job safe and the connections reliable.",
        [{"Type": "Essential", "How it works": "-", "Good": "-", "Bad": "-", "Best for": "-"}],
        "Buy or borrow these before you start.",
        ["Digital multimeter rated CAT III 1000 V DC (to measure your string voltage safely).",
         "MC4 crimp tool + MC4 spanners; cable cutter and stripper for 2.5-6 mm².",
         f"Hydraulic lug crimper for {(c['bat_cable'] or {}).get('Chosen (mm²)', 'battery')} mm² cable (if you have a battery).",
         "Insulated screwdrivers and spanners (1000 V), torque wrench.",
         "Drill with masonry bits, spirit level, phone angle app, measuring tape, marker and cable labels.",
         "Safety: insulated gloves, safety glasses, non-slip shoes, harness/rope for roof work, opaque sheet to cover panels."],
        ["Multimeter must show the CAT rating and 1000 V DC on the case."], None,
        ["Check every tool before climbing the roof; never work alone on a roof."], ["Cheap multimeters without CAT rating on PV strings."],
        "Book §117-§118")


def component_guide(pkg, design, x, ii) -> list[dict]:
    """Cards for every component relevant to the system type (grid_tied / hybrid_backup / off_grid)."""
    if x.mode not in MODES:
        raise ValueError(f"Unknown system type {x.mode!r}")
    c = _ctx(pkg, design, x, ii)
    cards = [_panels(c, pkg), _mounting(c, pkg), _pv_cable(c, pkg)]
    if c["string_fuse"]:
        cards.append(_string_fuse(c, pkg))
    cards += [_dc_isolator(c, pkg), _dc_spd(c, pkg)]
    if x.mode == "off_grid":
        cards.append(_controller(c, pkg))
    cards.append(_inverter(c, pkg))
    if x.mode in ("hybrid_backup", "off_grid"):
        cards += [_battery(c, pkg), _battery_cable(c, pkg)]
    cards.append(_ac_protection(c, pkg))
    if x.mode == "hybrid_backup":
        cards.append(_changeover(c, pkg))
    cards += [_earthing(c, pkg), _lightning(c, pkg)]
    if x.mode in ("grid_tied", "hybrid_backup"):
        cards.append(_meter(c, pkg))
    cards += [_monitoring(c, pkg), _tools(c, pkg)]
    return cards


def series_parallel_explainer(pkg) -> dict:
    """Series vs parallel for this system's panels and batteries, with its own numbers."""
    s = pkg.strings or {}
    ns, np_ = s.get("modules_per_string"), s.get("strings")
    out = {
        "rule": "SERIES (+ of one to − of the next): voltages add, current stays the same. PARALLEL (+ to +, − to −): "
                "currents add, voltage stays the same. Power = volts × amps either way.",
        "panels": (f"{ns} panels in series per string × {np_} string(s). String voltage: about {_n(s.get('string_vmp_stc_v'))} V "
                   f"working, {_n(s.get('string_voc_stc_v'))} V open-circuit at 25 °C, up to {_n(s.get('string_voc_cold_v'))} V "
                   f"on the coldest morning ({_n(s.get('t_min_c'), 1)} °C) and down to {_n(s.get('string_vmp_hot_v'))} V "
                   f"working on a hot afternoon. Your {s.get('pv_input', 'inverter')} accepts: {s.get('pv_input_limits', '')}. "
                   f"Allowed string length for your equipment: {s.get('n_min')} to {s.get('n_max')} panels."),
        "why_not_more": ("Too many panels in series → cold-morning voltage above the inverter limit → the inverter is "
                         "destroyed (not covered by warranty). Too few → voltage below the MPPT window on hot days → "
                         "the inverter stops or harvests little."),
        "mismatch": ("Every string joined in parallel must have the same number of the same panels facing the same way; "
                     "otherwise the strings fight each other and the system loses power."),
    }
    if s.get("battery_series"):
        out["batteries"] = (f"{s.get('battery_series')} in series × {s.get('battery_parallel')} in parallel = "
                            f"{_n(s.get('battery_kwh'), 1)} kWh. Series raises voltage to match the inverter; parallel "
                            "adds Ah (hours of backup). Use identical batteries; for parallel strings take + from the "
                            "first battery and − from the last (diagonal), with equal-length links (book §107).")
    return out
