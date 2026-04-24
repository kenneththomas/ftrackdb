from models import RelayTeam

def parse_time(time_str):
    if ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
    try:
        return float(time_str)
    except:
        return float('inf')

def format_relay_time(total_seconds):
    minutes = int(total_seconds // 60)
    seconds = total_seconds - minutes * 60
    return f"{minutes}:{seconds:05.2f}"

def is_relay_event(event):
    """Check if an event name is a relay event."""
    return event in RelayTeam.RELAY_CONFIG or event.endswith(' Relay')

def calculate_relay_results(splits, relay_type):
    """
    Calculate relay results from splits (old assumption mechanic).
    splits: list of tuples containing (athlete, result, date, meet, team)
    relay_type: string like '100m RS', '200m RS', '400m RS', '800m RS'
    """
    if len(splits) < 1:
        return []

    sorted_splits = sorted(splits, key=lambda x: parse_time(x[1]))
    best_splits = sorted_splits[:4]
    total_time = sum(parse_time(x[1]) for x in best_splits)

    formatted_time = format_relay_time(total_time)
    members = [split[0] for split in best_splits]

    relay_name = f"4x{relay_type.replace(' RS', '')}"

    first_split = best_splits[0]

    return [{
        'date': first_split[2],
        'meet': first_split[3],
        'event': relay_name,
        'result': formatted_time,
        'team': first_split[4],
        'athletes': members,
        'splits': [(split[0], split[1]) for split in best_splits],
        'result_id': None
    }]

def explicit_relay_to_display_dict(relay):
    """
    Convert an explicit relay dict (from RelayTeam.get_relays_for_*) into the display dict
    format used by templates.
    """
    legs = relay.get('legs', [])
    total_seconds = 0
    for leg in legs:
        total_seconds += parse_time(leg['split_result'])
    formatted_time = relay.get('total_result') or format_relay_time(total_seconds)
    members = [leg['athlete'] for leg in legs]
    splits = [(leg['athlete'], leg['split_result']) for leg in legs]
    return {
        'date': relay['date'],
        'meet': relay['meet'],
        'event': relay['event'],
        'result': formatted_time,
        'team': relay['team'],
        'athletes': members,
        'splits': splits,
        'legs': legs,
        'team_designation': relay.get('team_designation', 'A'),
        'relay_time_numeric': total_seconds,
        'result_id': None
    }
