"""Nepal reference data used by the app. Coordinates are approximate city centres (users can enter
exact Google Maps coordinates). Grid facts are general; tariffs and prices live in nepal_data and
must carry a source and date."""

from __future__ import annotations

# name -> (latitude, longitude, province)
NEPAL_SITES: dict[str, tuple[float, float, str]] = {
    "Kathmandu": (27.7172, 85.3240, "Bagmati"), "Lalitpur": (27.6644, 85.3188, "Bagmati"),
    "Bhaktapur": (27.6710, 85.4298, "Bagmati"), "Hetauda": (27.4284, 85.0322, "Bagmati"),
    "Bharatpur (Chitwan)": (27.6833, 84.4333, "Bagmati"), "Dhulikhel": (27.6200, 85.5400, "Bagmati"),
    "Biratnagar": (26.4525, 87.2718, "Koshi"), "Dharan": (26.8125, 87.2836, "Koshi"),
    "Damak": (26.6603, 87.7031, "Koshi"), "Ilam": (26.9094, 87.9282, "Koshi"),
    "Dhankuta": (26.9833, 87.3333, "Koshi"), "Janakpur": (26.7288, 85.9254, "Madhesh"),
    "Birgunj": (27.0104, 84.8770, "Madhesh"), "Rajbiraj": (26.5397, 86.7470, "Madhesh"),
    "Pokhara": (28.2096, 83.9856, "Gandaki"), "Gorkha": (28.0000, 84.6333, "Gandaki"),
    "Jomsom (Mustang)": (28.7804, 83.7307, "Gandaki"), "Butwal": (27.7006, 83.4483, "Lumbini"),
    "Bhairahawa (Siddharthanagar)": (27.5047, 83.4573, "Lumbini"), "Tansen (Palpa)": (27.8673, 83.5467, "Lumbini"),
    "Nepalgunj": (28.0500, 81.6167, "Lumbini"), "Ghorahi (Dang)": (28.0400, 82.4900, "Lumbini"),
    "Birendranagar (Surkhet)": (28.6019, 81.6339, "Karnali"), "Jumla": (29.2747, 82.1838, "Karnali"),
    "Dhangadhi": (28.6833, 80.6000, "Sudurpashchim"), "Mahendranagar": (28.9636, 80.1778, "Sudurpashchim"),
    "Dadeldhura": (29.2984, 80.5806, "Sudurpashchim"),
}

GRID = {"lv_single_phase_v": 230, "lv_three_phase_v": 400, "frequency_hz": 50,
        "distribution_kv": [11, 33], "transmission_kv": [66, 132, 220, 400]}


_CHOICES = {f"{n} - {p} Province": n for n, (_, _, p) in NEPAL_SITES.items()}


def site_choices() -> list[str]:
    return list(_CHOICES)


def site_coords(choice: str) -> tuple[float, float]:
    lat, lon, _ = NEPAL_SITES[_CHOICES[choice]]
    return lat, lon


def site_name(choice: str) -> str:
    return _CHOICES[choice]
