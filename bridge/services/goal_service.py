"""Donation goal parsing and calculation service."""

import re


def parse_amount(val) -> float:
    """Extract numeric float from strings like '500 ₽', '1 500,50 RUB', or raw numbers."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(" ", "").replace("\xa0", "").replace(",", ".")
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            pass
    return 0.0
