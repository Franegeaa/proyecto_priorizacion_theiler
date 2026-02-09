import sys
import os
from datetime import datetime, timedelta, time, date
import pandas as pd

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.utils.config_loader import sumar_horas_habiles, proximo_dia_habil, es_feriado

def test_sumar_horas_habiles():
    # Mock config
    cfg = {
        "feriados": {
            date(2023, 12, 25) # Christmas
        }
    }

    # Case 1: Simple addition within same day
    # Monday 10:00 + 2 hours -> Monday 12:00
    start = datetime(2023, 12, 4, 10, 0) # Monday
    result = sumar_horas_habiles(start, 2.0, cfg)
    expected = datetime(2023, 12, 4, 12, 0)
    assert result == expected, f"Case 1 Failed: {result} != {expected}"
    print("Case 1 Passed")

    # Case 2: Crossing midnight (business day)
    # Monday 20:00 + 5 hours -> Tuesday 01:00
    start = datetime(2023, 12, 4, 20, 0)
    result = sumar_horas_habiles(start, 5.0, cfg)
    expected = datetime(2023, 12, 5, 1, 0)
    assert result == expected, f"Case 2 Failed: {result} != {expected}"
    print("Case 2 Passed")

    # Case 3: Crossing weekend
    # Friday 20:00 + 5 hours -> Monday 01:00
    # Friday 20:00 to Friday 23:59:59... = ~4 hours
    # Remaining ~1 hour should go to Monday
    start = datetime(2023, 12, 1, 20, 0) # Friday
    result = sumar_horas_habiles(start, 5.0, cfg)
    expected = datetime(2023, 12, 4, 1, 0) # Monday
    assert result == expected, f"Case 3 Failed: {result} != {expected}"
    print("Case 3 Passed")

    # Case 4: Crossing Holiday
    # Sunday 24th Dec 20:00 + 5 hours -> Tuesday 26th 01:00 (Skip Mon 25th)
    # Wait, Sunday is already skipped.
    # Let's try: Friday 22nd 20:00 + 5 hours -> Tuesday 26th 01:00 (Skip Sat, Sun, Mon 25th)
    # Friday 22nd 20:00 -> Friday 24:00 (4 hours used)
    # Remaining 1 hour.
    # Sat 23 (skip), Sun 24 (skip), Mon 25 (holiday, skip)
    # Tue 26 00:00 + 1 hour -> Tue 26 01:00
    
    # Update mock config with correct date object
    cfg["feriados"] = {date(2023, 12, 25)}
    
    start = datetime(2023, 12, 22, 20, 0) # Friday
    result = sumar_horas_habiles(start, 5.0, cfg)
    expected = datetime(2023, 12, 26, 1, 0) # Tuesday
    assert result == expected, f"Case 4 Failed: {result} != {expected}"
    print("Case 4 Passed")

    # Case 5: 72 hours (3 days) starting Friday
    # Friday 12:00 + 72 hours
    # Fri 12:00 -> Fri 24:00 (12h)
    # Sat/Sun skip
    # Mon 00:00 -> Mon 24:00 (24h) -> Total 36h
    # Tue 00:00 -> Tue 24:00 (24h) -> Total 60h
    # Wed 00:00 -> Wed 12:00 (12h) -> Total 72h
    start = datetime(2023, 12, 1, 12, 0) # Friday
    result = sumar_horas_habiles(start, 72.0, cfg)
    expected = datetime(2023, 12, 6, 12, 0) # Wednesday
    assert result == expected, f"Case 5 Failed: {result} != {expected}"
    print("Case 5 Passed")

if __name__ == "__main__":
    test_sumar_horas_habiles()
