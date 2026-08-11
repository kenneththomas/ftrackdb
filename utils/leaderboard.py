"""Leaderboard query and ranking helpers.

The route intentionally delegates all result comparison to this module.  Keeping
the rules in Python makes time, decimal field, and feet/inches results behave the
same way for personal bests, full result lists, and Stagger views.
"""

from collections import defaultdict
from datetime import date, timedelta
import math
import re

from utils.field_utils import parse_field_result
from utils.relay_utils import calculate_relay_results, explicit_relay_to_display_dict, parse_time


PER_PAGE_OPTIONS = (25, 50, 100)
FIELD_EVENT_TERMS = (
    "jump", "vault", "shot", "discus", "javelin", "hammer", "weight", "throw",
)


def is_relay_event(event):
    return bool(event) and (event.startswith("4x") or event in {"DMR", "SMR"})


def is_time_event(event):
    """Return whether the event is ranked with the lowest result first."""
    normalized = (event or "").strip().lower()
    return bool(normalized) and not any(term in normalized for term in FIELD_EVENT_TERMS)


def result_value(result, timed):
    """Parse a display result into a sortable numeric value, or return None."""
    if result is None:
        return None
    raw = str(result).strip()
    if not raw:
        return None
    # Common result annotations (q, Q, w) should not invalidate a mark.
    raw = re.sub(r"\s*[A-Za-z]+$", "", raw).strip()
    value = parse_time(raw) if timed else parse_field_result(raw)
    if not math.isfinite(value) or value < 0:
        return None
    return value


def date_bounds(period, today=None):
    """Translate a period query value into inclusive ISO date boundaries."""
    today = today or date.today()
    if period in {"last_year", "last_365"}:
        return (today - timedelta(days=365)).isoformat(), None
    if period.startswith("year:"):
        try:
            year = int(period.split(":", 1)[1])
        except (TypeError, ValueError):
            return None, None
        if 1900 <= year <= 2200:
            return f"{year:04d}-01-01", f"{year:04d}-12-31"
    return None, None


def period_label(period):
    if period in {"last_year", "last_365"}:
        return "Last 365 days"
    if period.startswith("year:"):
        return period.split(":", 1)[1]
    return "All time"


def event_catalog(cursor, relay_config):
    """Return event metadata for the picker, including legacy RS relays."""
    cursor.execute(
        """SELECT Event, COUNT(*) AS result_count
           FROM Results
           WHERE Event IS NOT NULL AND TRIM(Event) != ''
           GROUP BY Event"""
    )
    raw_counts = {row[0].strip(): row[1] for row in cursor.fetchall()}
    catalog = {}
    for event, count in raw_counts.items():
        if event.endswith(" RS"):
            relay_event = f"4x{event[:-3].strip()}"
            catalog.setdefault(relay_event, {"name": relay_event, "count": 0, "relay": True})
            # Four splits represent approximately one relay result.
            catalog[relay_event]["count"] += max(1, count // 4)
        else:
            catalog[event] = {"name": event, "count": count, "relay": is_relay_event(event)}

    cursor.execute(
        """SELECT Event, COUNT(*) FROM RelayTeams
           WHERE Event IS NOT NULL AND TRIM(Event) != '' GROUP BY Event"""
    )
    for event, count in cursor.fetchall():
        event = event.strip()
        catalog.setdefault(event, {"name": event, "count": 0, "relay": True})
        catalog[event]["count"] += count

    # Configured relay types remain discoverable once they have data; arbitrary
    # explicit relay names are also supported by the catalog above.
    for event in relay_config:
        if event in catalog:
            catalog[event]["relay"] = True

    return sorted(catalog.values(), key=lambda item: (not item["relay"], item["name"].lower()))


def available_years(cursor):
    cursor.execute(
        """SELECT DISTINCT SUBSTR(Date, 1, 4) FROM Results
           WHERE Date GLOB '[0-9][0-9][0-9][0-9]-*'
           UNION
           SELECT DISTINCT SUBSTR(Date, 1, 4) FROM RelayTeams
           WHERE Date GLOB '[0-9][0-9][0-9][0-9]-*'
           ORDER BY 1 DESC"""
    )
    return [row[0] for row in cursor.fetchall() if row[0]]


def _best_rows(rows, lower_is_better):
    best = {}
    for row in rows:
        current = best.get(row["athlete"])
        if current is None:
            best[row["athlete"]] = row
            continue
        is_better = row["value"] < current["value"] if lower_is_better else row["value"] > current["value"]
        if is_better or (row["value"] == current["value"] and row["date"] > current["date"]):
            best[row["athlete"]] = row
    return list(best.values())


def rank_individual_rows(raw_rows, event, best_only=True, stagger_scores=None):
    """Normalize, filter, sort, and competition-rank individual results."""
    timed = is_time_event(event)
    rows = []
    for raw in raw_rows:
        value = result_value(raw[1], timed)
        if value is None:
            continue
        rows.append({
            "athlete": raw[0], "result": raw[1], "team": raw[2] or "Independent",
            "date": raw[3] or "", "meet": raw[4] or "", "value": value,
            "score": None,
        })

    # Stagger is an athlete rating, so it always has one representative result
    # per athlete even if the all-performances toggle was requested.
    if stagger_scores is not None:
        rows = _best_rows(rows, timed)
        rows = [row for row in rows if row["athlete"] in stagger_scores]
        for row in rows:
            row["score"] = stagger_scores[row["athlete"]]
        rows.sort(key=lambda row: (-row["score"], row["value"] if timed else -row["value"], row["athlete"].lower()))
        tie_value = lambda row: row["score"]
    else:
        if best_only:
            rows = _best_rows(rows, timed)
        rows.sort(key=lambda row: (row["value"] if timed else -row["value"], row["athlete"].lower(), row["date"]), reverse=False)
        tie_value = lambda row: row["value"]

    previous = object()
    rank = 0
    for index, row in enumerate(rows, start=1):
        value = tie_value(row)
        if value != previous:
            rank = index
            previous = value
        row["rank"] = rank
    return rows


def fetch_individual_rankings(cursor, event, start_date=None, end_date=None, best_only=True, sort_by="performance"):
    query = "SELECT Athlete, Result, Team, Date, Meet_Name FROM Results WHERE Event = ?"
    params = [event]
    if start_date:
        query += " AND Date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND Date <= ?"
        params.append(end_date)
    cursor.execute(query, params)
    raw_rows = cursor.fetchall()

    scores = None
    if sort_by == "stagger":
        cursor.execute("SELECT athlete, score FROM StaggerScores WHERE event = ?", (event,))
        scores = {row[0]: row[1] for row in cursor.fetchall()}
    return rank_individual_rows(raw_rows, event, best_only=best_only, stagger_scores=scores)


def fetch_relay_rankings(cursor, event, start_date=None, end_date=None, best_only=True):
    """Load legacy and explicit relay records and return normalized rankings."""
    relays = []
    if event.startswith("4x"):
        split_event = f"{event[2:]} RS"
        query = "SELECT Date, Meet_Name, Team, Athlete, Result FROM Results WHERE Event = ?"
        params = [split_event]
        if start_date:
            query += " AND Date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND Date <= ?"
            params.append(end_date)
        cursor.execute(query, params)
        grouped = defaultdict(list)
        for row in cursor.fetchall():
            grouped[(row[2], row[0], row[1])].append((row[3], row[4], row[0], row[1], row[2]))
        for splits in grouped.values():
            if len(splits) >= 4:
                relays.extend(calculate_relay_results(splits, split_event))

    query = """SELECT Relay_ID, Date, Meet_Name, Team, Event, Total_Result, Team_Designation
               FROM RelayTeams WHERE Event = ?"""
    params = [event]
    if start_date:
        query += " AND Date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND Date <= ?"
        params.append(end_date)
    cursor.execute(query, params)
    explicit = cursor.fetchall()
    relay_ids = [row[0] for row in explicit]
    legs_by_relay = defaultdict(list)
    if relay_ids:
        placeholders = ",".join("?" for _ in relay_ids)
        cursor.execute(
            f"SELECT Relay_ID, Leg_Number, Athlete, Split_Event, Split_Result FROM RelayLegs WHERE Relay_ID IN ({placeholders}) ORDER BY Relay_ID, Leg_Number",
            relay_ids,
        )
        for row in cursor.fetchall():
            legs_by_relay[row[0]].append({"leg_number": row[1], "athlete": row[2], "split_event": row[3], "split_result": row[4]})
    for row in explicit:
        relays.append(explicit_relay_to_display_dict({
            "relay_id": row[0], "date": row[1], "meet": row[2], "team": row[3],
            "event": row[4], "total_result": row[5], "team_designation": row[6],
            "legs": legs_by_relay[row[0]],
        }))

    ranked = []
    for relay in relays:
        value = result_value(relay.get("result"), True)
        if value is not None:
            relay["value"] = value
            relay["team"] = relay.get("team") or "Independent"
            ranked.append(relay)
    ranked.sort(key=lambda row: (row["value"], row["team"].lower(), row.get("date", "")))
    if best_only:
        best = {}
        for row in ranked:
            best.setdefault(row["team"], row)
        ranked = list(best.values())
        ranked.sort(key=lambda row: (row["value"], row["team"].lower()))
    previous = object()
    rank = 0
    for index, row in enumerate(ranked, start=1):
        if row["value"] != previous:
            rank = index
            previous = row["value"]
        row["rank"] = rank
    return ranked


def paginate(rows, page, per_page):
    total = len(rows)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(page, 1), total_pages)
    start = (page - 1) * per_page
    return rows[start:start + per_page], page, total_pages, total

