from datetime import datetime

from backend.data import Impression


def make_impression(
    history: int = 12, clicks: int = 2, non_clicks: int = 10, user_id: str = "U1"
) -> Impression:
    shown = tuple((f"C{i}", 1) for i in range(clicks)) + tuple(
        (f"N{i}", 0) for i in range(non_clicks)
    )
    return Impression(
        impression_id="1",
        user_id=user_id,
        time=datetime(2019, 11, 15, 9, 0),
        history=tuple(f"H{i}" for i in range(history)),
        shown=shown,
    )
