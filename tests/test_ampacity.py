import pytest

from ecalc.calc import ValidationError
from ecalc.calc.ampacity import cable_capacity, device_rating, size_for_current


def test_device_rating_125_percent():
    assert device_rating(21.7) == 32          # 1.25 x 21.7 = 27.1 -> next standard 32 A
    assert device_rating(8.0) == 10           # 10 A exactly
    assert device_rating(60.3) == 80          # battery 60 A -> 75.4 -> 80 A


def test_cable_for_device_with_ambient():
    assert size_for_current(32) == 4          # 4 mm² = 32 A at 30 °C
    # 40 °C: 4 mm² -> 32 x 0.87 = 27.8 < 32 -> 6 mm² (41 x 0.87 = 35.7)
    assert size_for_current(32, 40) == 6
    assert cable_capacity(10, 40) == pytest.approx(57 * 0.87)
    assert size_for_current(80) == 25         # 16 mm² 76 A < 80; 25 mm² 101 A


def test_limits():
    with pytest.raises(ValidationError):
        size_for_current(1000)
    with pytest.raises(ValidationError):
        device_rating(500)
