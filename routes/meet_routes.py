from flask import Blueprint, render_template
from models import Result
from utils.relay_utils import parse_time

# Create blueprint
meet_bp = Blueprint('meet', __name__)

@meet_bp.route('/meet/<meet_name>')
def meet_results(meet_name):
    raw_results = Result.get_meet_results(meet_name)
    # Group standard results by (event, date)
    events = {}
    # Gather relay splits separately for computing the combined relay result
    relay_by_team = {}
    
    for row in raw_results:
        date, athlete, event, result, team = row
        # For relay splits, process them twice:
        # 1. Include them in the raw results (as "400m RS Relay Splits")
        # 2. Also include them in relay_by_team for computing the combined result.
        if event == "400m RS":
            # Group for combined relay calculations by team and date
            relay_key = (team, date)
            if relay_key not in relay_by_team:
                relay_by_team[relay_key] = []
            relay_by_team[relay_key].append({
                'date': date,
                'athlete': athlete,
                'result': result
            })
            # Also add the raw split entry to be displayed separately.
            event_key = (event, date)
            if event_key not in events:
                events[event_key] = []
            events[event_key].append({
                'athlete': athlete,
                'result': result,
                'team': team
            })
        else:
            event_key = (event, date)
            if event_key not in events:
                events[event_key] = []
            events[event_key].append({
                'athlete': athlete,
                'result': result,
                'team': team
            })
    
    # Process relay splits: for each team and date grouping, if there are at least 4 splits,
    # select the fastest four and calculate the combined relay time.
    relay_results = []
    for (team, group_date), splits in relay_by_team.items():
        if len(splits) < 4:
            continue  # Skip groups with fewer than 4 splits
        sorted_splits = sorted(splits, key=lambda x: parse_time(x['result']))
        best_splits = sorted_splits[:4]
        total_time = sum(parse_time(s['result']) for s in best_splits)
        relay_date = group_date  # all splits in the group share the same date
        minutes = int(total_time // 60)
        seconds = total_time - minutes * 60
        formatted_time = f"{minutes}:{seconds:05.2f}"
        members = [s['athlete'] for s in best_splits]
        relay_results.append({
            'athlete': ', '.join(members),  # fallback display string
            'athletes': members,            # list of individual athletes for linking
            'result': formatted_time,
            'team': team,
            'relay_time_numeric': total_time,
            'date': relay_date
        })
    
    # Add computed combined relay results to the events dictionary.
    # They will appear under the event name "400m RS Relay".
    for rr in relay_results:
        key = ("400m RS Relay", rr['date'])
        if key not in events:
            events[key] = []
        events[key].append({
            'athlete': rr['athlete'],
            'athletes': rr.get('athletes'),
            'result': rr['result'],
            'team': rr['team'],
            'relay_time_numeric': rr['relay_time_numeric']
        })
    
    # Optional: for relay events, sort entries by the numeric relay time and assign places.
    for event_key, records in events.items():
        if event_key[0] == "400m RS Relay":
            records.sort(key=lambda x: x.get('relay_time_numeric', float('inf')))
        # Assign rankings (place numbers)
        for place, record in enumerate(records, start=1):
            record['place'] = place
    
    return render_template('meet.html', meet_name=meet_name, events=events) 