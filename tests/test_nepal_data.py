"""NEA domestic bill (ERC order 2078 p.74) - hand calculations."""
import pytest

from ecalc.calc import ValidationError
from ecalc.nepal_data import domestic_bill, site_temperatures


def test_15a_150_units():
    # service (101-250 band, 15 A) 125; energy 20x4 + 10x6.5 + 20x8 + 50x9.5 + 50x9.5 = 1255 -> 1380
    assert domestic_bill(150, 15) == pytest.approx(1380)


def test_15a_300_units_top_block():
    # service 175; energy 80 + 65 + 160 + 475 + 1425 (150 x 9.5) + 50 x 11 = 2755 -> 2930
    assert domestic_bill(300, 15) == pytest.approx(2930)


def test_5a_meter_rules():
    assert domestic_bill(18, 5) == pytest.approx(30)              # <= 20 units: free energy, Rs 30 service
    # 25 units on 5 A: first 20 at Rs 3 = 60, next 5 at 6.5 = 32.5, service 50 -> 142.5
    assert domestic_bill(25, 5) == pytest.approx(142.5)


def test_vat_only_above_50_units():
    assert domestic_bill(40, 15) == domestic_bill(40, 15, include_vat=True)
    assert domestic_bill(150, 15, include_vat=True) == pytest.approx(1380 * 1.05)


def test_invalid_meter():
    with pytest.raises(ValidationError):
        domestic_bill(100, 10)


def test_site_temperatures():
    assert site_temperatures("Jumla") == (-15.0, 33.3)
    assert site_temperatures("Dharan") is None


def test_monthly_bills_hand_case():
    """No sun -> no saving; flat-rate case checks the import/export arithmetic."""
    from ecalc.savings import monthly_bills
    dark = {m: [0.0] * 24 for m in range(1, 13)}
    rows = monthly_bills(dark, 1.0, [0.0] * 12, 5.0, "Flat - same all day (pumps, servers, cold rooms)", 15)
    assert all(r["Saving (Rs)"] == 0 for r in rows)
    assert rows[0]["Use (kWh)"] == 155 and rows[0]["Bill without solar (Rs)"] == round(domestic_bill(155, 15))
    # square sun 10:00-14:00 (4 h), 1 kWp, 4 kWh/kWp/day -> 1 kW for 4 h; flat load 0.5 kW (12 kWh/day)
    sun = [0.0] * 24
    for h in range(10, 14):
        sun[h] = 1000.0
    prof = {m: sun for m in range(1, 13)}
    r = monthly_bills(prof, 1.0, [4.0] * 12, 12.0, "Flat - same all day (pumps, servers, cold rooms)",
                      meter_amp=None, flat_rate_rs=10.0, export_rs=5.0)[0]       # January, 31 days
    # per day: import 20 h x 0.5 = 10 kWh, export 4 h x 0.5 = 2 kWh
    assert r["From grid (kWh)"] == 310 and r["To grid (kWh)"] == 62
    assert r["Bill without solar (Rs)"] == 3720                      # 372 kWh x 10
    assert r["Bill with solar (Rs)"] == 3100 - 310                   # 310 x 10 - 62 x 5
