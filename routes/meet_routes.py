from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Result, Team, Database, TeamScore
from utils.relay_utils import parse_time
from forms import MeetResultForm
from datetime import datetime, timedelta

# Create blueprint
meet_bp = Blueprint('meet', __name__)

def get_athlete_ranking(athlete, event, date, include_current=False):
    """Get athlete's ranking for an event as of the given date"""
    # Get date 1 year before the meet date
    meet_date = datetime.strptime(date, '%Y-%m-%d')
    one_year_ago = (meet_date - timedelta(days=365)).strftime('%Y-%m-%d')
    target_date = date if include_current else (meet_date - timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # For time events (lower is better)
        if 'm' in event or 'Mile' in event:
            cur.execute('''
                WITH RankedResults AS (
                    SELECT 
                        Athlete,
                        Result,
                        ROW_NUMBER() OVER (ORDER BY Result ASC) as rank
                    FROM Results 
                    WHERE Event = ? 
                    AND Date <= ?
                    AND Date >= ?
                    GROUP BY Athlete
                    HAVING Result = MIN(Result)
                )
                SELECT rank 
                FROM RankedResults 
                WHERE Athlete = ?
            ''', (event, target_date, one_year_ago, athlete))
        # For field events (higher is better)
        else:
            cur.execute('''
                WITH RankedResults AS (
                    SELECT 
                        Athlete,
                        Result,
                        ROW_NUMBER() OVER (ORDER BY Result DESC) as rank
                    FROM Results 
                    WHERE Event = ? 
                    AND Date <= ?
                    AND Date >= ?
                    GROUP BY Athlete
                    HAVING Result = MAX(Result)
                )
                SELECT rank 
                FROM RankedResults 
                WHERE Athlete = ?
            ''', (event, target_date, one_year_ago, athlete))
        
        result = cur.fetchone()
        return result[0] if result else None

def is_pr(athlete, event, result):
    """Check if a result is a PR for the athlete"""
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # Get all results for this athlete and event
        cur.execute('''
            SELECT Result 
            FROM Results 
            WHERE Athlete = ? AND Event = ?
            ORDER BY Result ASC
        ''', (athlete, event))
        all_results = [row[0] for row in cur.fetchall()]
        
        if not all_results:
            return True  # First time running this event
        
        # For time events, lower is better
        if 'm' in event or 'Mile' in event:
            return result == min(all_results)
        # For field events, higher is better
        else:
            return result == max(all_results)

@meet_bp.route('/meet/<meet_name>', methods=['GET', 'POST'])
def meet_results(meet_name):
    form = MeetResultForm()
    if form.validate_on_submit():
        # Insert the result for this meet
        data = {
            'date': form.date.data.strftime('%Y-%m-%d'),
            'athlete': form.athlete.data,
            'meet': meet_name,
            'event': form.event.data,
            'result': form.result.data,
            'team': form.team.data
        }
        Result.insert_result(data)
        # Clear cached team scores since we added a new result
        TeamScore.update_meet_scores(meet_name, {})
        flash('Result added!', 'success')
        return redirect(url_for('meet.meet_results', meet_name=meet_name))

    raw_results = Result.get_meet_results(meet_name)
    # Group standard results by (event, date)
    events = {}
    # Gather relay splits separately for computing the combined relay result
    relay_by_team = {}
    
    # Get all unique teams from the results
    teams = set()
    for row in raw_results:
        teams.add(row[4])  # team is at index 4
    
    # Get team logos for all teams
    team_logos = {}
    for team in teams:
        team_info = Team.get_team_info(team)
        if team_info and team_info.get('logo_url'):
            team_logos[team] = team_info['logo_url']

    # Get cached team scores
    cached_scores = TeamScore.get_meet_scores(meet_name)
    if cached_scores:
        sorted_teams = [(row[0], row[1]) for row in cached_scores]
    else:
        # Calculate team scores if not cached
        team_scores = {team: 0 for team in teams}
        
        # NCAA scoring system: 10-8-6-5-4-3-2-1
        ncaa_points = {
            1: 10,
            2: 8,
            3: 6,
            4: 5,
            5: 4,
            6: 3,
            7: 2,
            8: 1
        }
        
        for (event, date), results in events.items():
            # Skip relay splits as they're part of the relay event
            if event == "400m RS":
                continue
                
            # Sort results by place
            sorted_results = sorted(results, key=lambda x: x['place'])
            
            # Track current place and points
            current_place = 1
            tied_results = []
            
            for i, result in enumerate(sorted_results):
                # Skip if place is beyond 8th
                if result['place'] > 8:
                    continue
                    
                tied_results.append(result)
                
                # Check if next result has same place or if this is the last result
                if i == len(sorted_results) - 1 or sorted_results[i + 1]['place'] != result['place']:
                    # Calculate points for the tied places
                    total_points = 0
                    for place in range(current_place, current_place + len(tied_results)):
                        if place in ncaa_points:
                            total_points += ncaa_points[place]
                    
                    # Average the points for tied places
                    avg_points = total_points / len(tied_results)
                    
                    # Assign points to each tied result
                    for tied_result in tied_results:
                        team_scores[tied_result['team']] += avg_points
                    
                    # Move to next place after the ties
                    current_place += len(tied_results)
                    tied_results = []
        
        # Cache the calculated scores
        TeamScore.update_meet_scores(meet_name, team_scores)
        
        # Sort teams by score
        sorted_teams = sorted(team_scores.items(), key=lambda x: x[1], reverse=True)

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
                'team': team,
                'is_pr': is_pr(athlete, event, result),
                'ranking_before': get_athlete_ranking(athlete, event, date, include_current=False),
                'ranking_after': get_athlete_ranking(athlete, event, date, include_current=True)
            })
        else:
            event_key = (event, date)
            if event_key not in events:
                events[event_key] = []
            events[event_key].append({
                'athlete': athlete,
                'result': result,
                'team': team,
                'is_pr': is_pr(athlete, event, result),
                'ranking_before': get_athlete_ranking(athlete, event, date, include_current=False),
                'ranking_after': get_athlete_ranking(athlete, event, date, include_current=True)
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

    return render_template('meet.html', meet_name=meet_name, events=events, team_logos=team_logos, form=form, sorted_teams=sorted_teams)

@meet_bp.route('/meet/<old_name>/rename', methods=['POST'])
def rename_meet(old_name):
    new_name = request.form.get('new_name')
    meet_date = request.form.get('meet_date')
    
    if not new_name:
        flash('New meet name is required', 'error')
        return redirect(url_for('meet.meet_results', meet_name=old_name))
    
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        
        # If a date is provided, only rename results for that specific date
        if meet_date:
            cur.execute('''
                UPDATE Results 
                SET Meet_Name = ? 
                WHERE Meet_Name = ? AND Date = ?
            ''', (new_name, old_name, meet_date))
        else:
            # Otherwise rename all results for this meet
            cur.execute('''
                UPDATE Results 
                SET Meet_Name = ? 
                WHERE Meet_Name = ?
            ''', (new_name, old_name))
        
        conn.commit()
    
    flash(f'Meet renamed successfully to {new_name}', 'success')
    return redirect(url_for('meet.meet_results', meet_name=new_name))

@meet_bp.route('/meet/<meet_name>/calculate_scores', methods=['POST'])
def calculate_meet_scores(meet_name):
    # Get all results for this meet
    raw_results = Result.get_meet_results(meet_name)
    
    # Get all unique teams
    teams = set()
    for row in raw_results:
        teams.add(row[4])  # team is at index 4
    
    # Calculate team scores
    team_scores = {team: 0 for team in teams}
    
    # NCAA scoring system: 10-8-6-5-4-3-2-1
    ncaa_points = {
        1: 10,
        2: 8,
        3: 6,
        4: 5,
        5: 4,
        6: 3,
        7: 2,
        8: 1
    }
    
    # Group results by event and date
    events = {}
    for row in raw_results:
        date, athlete, event, result, team = row
        event_key = (event, date)
        if event_key not in events:
            events[event_key] = []
        events[event_key].append({
            'athlete': athlete,
            'result': result,
            'team': team
        })
    
    # Calculate places for each event
    for (event, date), results in events.items():
        # For time events (lower is better)
        if 'm' in event or 'Mile' in event:
            results.sort(key=lambda x: parse_time(x['result']))
        # For field events (higher is better)
        else:
            results.sort(key=lambda x: float(x['result']), reverse=True)
        
        # Assign places
        current_place = 1
        current_result = None
        tied_count = 0
        
        for i, result in enumerate(results):
            if current_result is None or result['result'] != current_result:
                current_place += tied_count
                tied_count = 0
                current_result = result['result']
            
            result['place'] = current_place
            tied_count += 1
    
    # Calculate scores for each event
    for (event, date), results in events.items():
        # Skip relay splits as they're part of the relay event
        if event == "400m RS":
            continue
            
        # Sort results by place
        sorted_results = sorted(results, key=lambda x: x['place'])
        
        # Track current place and points
        current_place = 1
        tied_results = []
        
        for i, result in enumerate(sorted_results):
            # Skip if place is beyond 8th
            if result['place'] > 8:
                continue
                
            tied_results.append(result)
            
            # Check if next result has same place or if this is the last result
            if i == len(sorted_results) - 1 or sorted_results[i + 1]['place'] != result['place']:
                # Calculate points for the tied places
                total_points = 0
                for place in range(current_place, current_place + len(tied_results)):
                    if place in ncaa_points:
                        total_points += ncaa_points[place]
                
                # Average the points for tied places
                avg_points = total_points / len(tied_results)
                
                # Assign points to each tied result
                for tied_result in tied_results:
                    team_scores[tied_result['team']] += avg_points
                
                # Move to next place after the ties
                current_place += len(tied_results)
                tied_results = []
    
    # Cache the calculated scores
    TeamScore.update_meet_scores(meet_name, team_scores)
    
    flash('Team scores have been recalculated!', 'success')
    return redirect(url_for('meet.meet_results', meet_name=meet_name)) 