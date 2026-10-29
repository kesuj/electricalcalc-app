"""Hands-on skills a first-time installer needs, written for this system, plus the honest legal stop-points.

Paraphrased from Boxwell, *Solar Electricity Handbook* (2012) installation, commissioning and maintenance
chapters (§117-§139) and updated with current practice ([modern]). Battery charge voltages are TYPICAL values
only - the battery manufacturer's datasheet always wins.
"""

from __future__ import annotations


def _n(v, d: int = 0) -> str:
    return f"{v:,.{d}f}" if isinstance(v, (int, float)) else str(v)


def skills(pkg, x) -> list[dict]:
    s = pkg.strings or {}
    voc_stc, voc_cold, ns = s.get("string_voc_stc_v"), s.get("string_voc_cold_v"), s.get("modules_per_string")
    battery = x.mode in ("hybrid_backup", "off_grid")
    lithium = str(x.chemistry).startswith("LiFePO4")
    per_panel_voc = voc_stc / ns if voc_stc and ns else None
    bat_cable = next((c for c in pkg.cable_schedule if c["Circuit"].startswith("Battery cable")), None)
    out = [
        {"title": "Using a multimeter safely",
         "why": "You will check voltage and polarity before every connection - it is the installer's most important tool.",
         "steps": ["Set the dial to DC volts (V with a straight line), range above 1000 V if manual-ranging.",
                   "Black probe in COM, red probe in V/Ω. Never use the 10 A / mA socket for voltage.",
                   f"Panel test: in sun, touch red to the panel + and black to −. Expect about {_n(per_panel_voc, 1)} V "
                   "(the panel's Voc). A minus sign means the probes are reversed.",
                   f"String test: with the DC isolator OFF, measure the whole string's + and −. Expect roughly {_n(voc_stc)} V "
                   f"at 25 °C (higher on a cold morning, up to {_n(voc_cold)} V). Write it in the commissioning record.",
                   "Continuity test (beep mode) only on cables that are disconnected at both ends.",
                   "Never measure current by putting the probes across a battery or a string - that is a short circuit."],
         "safety": ["Use a CAT III 1000 V DC meter with good probes.", "Keep fingers behind the probe guards."]},
        {"title": "Assembling and crimping MC4 connectors",
         "why": "Badly made MC4 joints are the most common cause of solar fires (book §120 stresses good connections).",
         "steps": ["Strip about 7 mm of insulation without nicking the copper strands.",
                   "Insert into the metal pin; crimp with an MC4 crimping tool in the matching die (4 or 6 mm²).",
                   "Pull hard on the pin - it must not move.",
                   "Push the pin into the housing until it clicks; tighten the back nut with MC4 spanners.",
                   "Male pin goes in the female housing for one polarity - follow the panel's own plugs: + lead gets the "
                   "connector that mates with the panel's − lead plug, and vice versa.",
                   "Check polarity with the multimeter before plugging in."],
         "safety": ["Never plug/unplug MC4 connectors while current flows - open the DC isolator first.",
                    "Never mix connector brands."]},
        {"title": "Fixing the frame to the roof and waterproofing",
         "why": "The frame must survive monsoon storms and the roof must not leak (book §123).",
         "steps": ["RCC flat roof: mark positions, drill with a masonry bit, clean the dust, set anchor bolts "
                   "(chemical or expansion), apply waterproof sealant around each one and over the base plate edges.",
                   "Tin / sloping roof: locate the purlins, use roof hooks or feet screwed into the purlins with EPDM "
                   "washers and roofing sealant; never fix to the sheet alone.",
                   "Check the tilt with a phone angle app and that rails are straight before fixing panels.",
                   "Pour water around fixings after installation and check inside for leaks."],
         "safety": ["Use a harness on sloping roofs and keep away from roof edges.", "Never work on a wet roof."]},
        {"title": "Cable routing, conduit and labelling",
         "why": "Neat, protected cables last 25 years; labels keep the next person safe.",
         "steps": ["Run + and − of each circuit together in UV-proof conduit or tied to the rails.",
                   "Use cable glands where cables enter boxes; leave drip loops so water runs off.",
                   "Label: 'SOLAR DC - LIVE IN DAYLIGHT' at the isolator, inverter and DB; 'Two power sources' at the DB "
                   "and meter; circuit names on every breaker."],
         "safety": ["Keep DC and AC cables apart where possible.", "No joints inside walls."]},
        {"title": "Measuring earth resistance",
         "why": "A good earth makes fault and lightning protection work.",
         "steps": ["Best: an earth resistance tester (3-pole method) - hire one or ask the electrician; record the value.",
                   "Target: as low as practical and within your local electrical rules (ask the electrician/NEA what value "
                   "they require) - add a second rod if it is high.",
                   "Simple check without a tester: the RCD must trip when its test button is pressed, and the multimeter "
                   "should show near 0 Ω continuity between each panel frame and the earth bar (system OFF)."],
         "safety": ["Disconnect the earth conductor only with the whole system OFF."]},
    ]
    if battery:
        out.append({
            "title": "Crimping battery lugs and tightening terminals",
            "why": "Battery currents are large; a loose or badly crimped lug gets hot enough to melt (book §125).",
            "steps": [f"Cut the {(bat_cable or {}).get('Chosen (mm²)', '')} mm² cable square; strip exactly the lug barrel depth.",
                      "Insert fully, crimp with a hydraulic crimper using the die for that cable size (two crimps for big lugs).",
                      "Slide on heat-shrink (red +, black −) and shrink it with a hot-air gun.",
                      "Tighten terminal bolts with a torque wrench to the battery manual's value; re-check after one week."],
            "safety": ["Remove rings and watches; use insulated spanners.", "Connect the − cable last, disconnect it first.",
                       "Never lay tools on top of batteries."]})
        out.append({
            "title": "Setting up the inverter / charger for your battery",
            "why": "Wrong charge settings shorten battery life or damage it.",
            "steps": ["Select the battery type in the menu: 'LiFePO4/Lithium' (use the battery's communication mode "
                      "CAN/RS485 if both support it) or 'Flooded/AGM' for lead-acid." ,
                      "If you must enter voltages manually, copy them from the BATTERY datasheet: charge (absorption) "
                      "voltage, float voltage, low-voltage cut-off, max charge current.",
                      ("Typical values for a 48 V (16-cell) LiFePO4 battery, ONLY if the datasheet gives none: charge about "
                       "54-56 V, cut-off about 46-48 V; never above 57.6 V = 3.6 V per cell (NEPQA-2025 high-voltage "
                       "disconnect). For 24 V divide by 2." if lithium else
                       "Lead-acid: use the battery maker's absorption/float values for its temperature; typical figures "
                       "vary by type - never guess."),
                      "Set the maximum charge current at or below the battery's recommended value.",
                      "Hybrid: set the backup reserve (e.g. keep 30-50 % for power cuts) and the grid charging on/off."],
            "safety": ["Typical values are a fallback only - the battery datasheet always wins."]})
    out += [
        {"title": "First switch-on and safe shutdown",
         "why": "The order protects the electronics (book §107, §126-§128).",
         "steps": (["Switch ON: battery isolator → inverter → (wait for battery detection) → PV DC isolator → AC output "
                    "breaker → loads one by one."] if battery else
                   ["Switch ON: AC breaker (grid) → inverter → PV DC isolator. Watch the display for grid detection."]) +
                  ["Check the display: PV voltage close to your string voltage, battery voltage, no fault codes.",
                   "Shutdown: loads/AC breaker OFF → PV DC isolator OFF → inverter OFF" +
                   (" → battery isolator OFF." if battery else ".")],
         "safety": ["Never open the battery isolator while the inverter is running heavy loads."]},
        {"title": "Monthly self-check (10 minutes)",
         "why": "Catches problems before they become expensive (book §131-§139).",
         "steps": ["Compare this month's energy in the app with the expected monthly figure in your report.",
                   "Look at panels for dirt, bird droppings, cracks; clean with water and a soft brush early morning.",
                   "Check SPD windows (green = OK), smell/heat at terminals, loose cables, rust on the frame.",
                   "Press the RCD test button.", "Battery: no swelling, terminals clean and tight" +
                   ("." if lithium else "; top up distilled water in flooded batteries.")],
         "safety": ["Do not hose panels in hot afternoon sun (thermal shock); never use detergent or pressure washers."]},
    ]
    return out


def legal_and_safety_stop_points(x) -> list[str]:
    """Kept for compatibility: the corrected wording lives in research_2026 (no house-wiring licence law found)."""
    from .research_2026 import legal_points_2026
    return legal_points_2026(x)
