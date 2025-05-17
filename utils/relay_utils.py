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

def calculate_relay_results(splits, relay_type):
    """
    Calculate relay results from splits
    splits: list of tuples containing (athlete, result)
    relay_type: string like '200m RS', '400m RS', '800m RS'
    """
    relay_results = []
    
    # Process splits directly like the original code
    if len(splits) < 4:
        return []
        
    sorted_splits = sorted(splits, key=lambda x: parse_time(x[1]))
    best_splits = sorted_splits[:4]
    total_time = sum(parse_time(x[1]) for x in best_splits)
    
    minutes = int(total_time // 60)
    seconds = total_time - minutes * 60
    formatted_time = f"{minutes}:{seconds:05.2f}"
    members = [split[0] for split in best_splits]
    
    # Convert relay type to full name (e.g., '400m RS' -> '4x400m')
    relay_name = f"4x{relay_type.replace(' RS', '')}"
    
    return [{
        'date': splits[0][2],  # Assuming date is third element
        'meet': splits[0][3],  # Assuming meet is fourth element
        'event': f"{relay_name} Relay",
        'result': formatted_time,
        'team': splits[0][4],  # Assuming team is fifth element
        'athletes': members,
        'result_id': None
    }] 