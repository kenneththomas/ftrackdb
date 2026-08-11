"""Deterministic performance-ranking and Stagger placement helpers.

This module is deliberately database-agnostic.  Routes and models provide raw
rows; every consumer gets the same event classification, mark parsing, best-mark
selection, tie handling, and placement rules.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from utils.leaderboard import is_time_event, result_value


RANKING_ALGORITHM_VERSION = 2
RANKING_WINDOW_DAYS = 365


def canonical_event(event):
    return (event or "").strip()


def rank_performances(rows, event):
    """Return athlete -> {rank, mark, value} using one best valid mark each.

    ``rows`` may be sqlite rows, mappings, or tuples whose first two values are
    athlete and display mark.  Competition ranking is used (1, 2, 2, 4).
    """
    event = canonical_event(event)
    timed = is_time_event(event)
    best = {}
    for row in rows:
        if hasattr(row, "keys"):
            athlete, mark = row["athlete"], row["result"]
        else:
            athlete, mark = row[0], row[1]
        athlete = (athlete or "").strip()
        value = result_value(mark, timed)
        if not athlete or value is None:
            continue
        current = best.get(athlete)
        better = current is None or (value < current["value"] if timed else value > current["value"])
        if better:
            best[athlete] = {"mark": str(mark).strip(), "value": value}

    ordered = sorted(
        best.items(),
        key=lambda item: (
            item[1]["value"] if timed else -item[1]["value"],
            item[0].casefold(),
        ),
    )
    ranked = {}
    previous_value = object()
    rank = 0
    for index, (athlete, data) in enumerate(ordered, start=1):
        if data["value"] != previous_value:
            rank = index
            previous_value = data["value"]
        ranked[athlete] = {"rank": rank, **data}
    return ranked


def ranking_window_start(date_text):
    meet_date = datetime.strptime(date_text, "%Y-%m-%d")
    return (meet_date - timedelta(days=RANKING_WINDOW_DAYS)).strftime("%Y-%m-%d")


def placements_from_rows(rows):
    """Build (event, date) -> [{athlete, place}] from raw result rows.

    Expected row order is date, athlete, event, result. Relay splits/team events
    are excluded because Stagger is an individual-event rating.
    """
    grouped = defaultdict(list)
    for row in rows:
        date, athlete, event, result = row[:4]
        event = canonical_event(event)
        if not event or event.endswith(" RS") or event.endswith(" Relay"):
            continue
        grouped[(event, date)].append((athlete, result))

    placements = {}
    for key, records in grouped.items():
        ranked = rank_performances(records, key[0])
        placements[key] = [
            {"athlete": athlete, "place": data["rank"]}
            for athlete, data in sorted(ranked.items(), key=lambda item: (item[1]["rank"], item[0].casefold()))
        ]
    return placements
