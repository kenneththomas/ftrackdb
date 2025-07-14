from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import Result, Team, Database, TeamScore, AthleteRanking, Comment
from utils.relay_utils import parse_time
from forms import MeetResultForm, CommentForm
from datetime import datetime, timedelta

# Create blueprint
meet_bp = Blueprint('meet', __name__)

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
    comment_form = CommentForm()
    
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
        # Clear cached team scores and rankings since we added a new result
        TeamScore.update_meet_scores(meet_name, {})
        AthleteRanking.update_meet_rankings(meet_name, [])
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
    
    # Initialize sorted_teams as empty list in case no results exist
    sorted_teams = []
    
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
        
        # Initialize sorted_teams as empty list in case no events exist
        sorted_teams = []
        
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

    # Get cached rankings
    cached_rankings = AthleteRanking.get_meet_rankings(meet_name)
    rankings_dict = {}
    if cached_rankings:
        for row in cached_rankings:
            event, date, athlete, ranking_before, ranking_after = row
            key = (event, date, athlete)
            rankings_dict[key] = {
                'ranking_before': ranking_before,
                'ranking_after': ranking_after
            }

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
            
            # Get rankings from cache or calculate if not available
            ranking_key = (event, date, athlete)
            rankings = rankings_dict.get(ranking_key, {})
            
            events[event_key].append({
                'athlete': athlete,
                'result': result,
                'team': team,
                'is_pr': is_pr(athlete, event, result),
                'ranking_before': rankings.get('ranking_before'),
                'ranking_after': rankings.get('ranking_after')
            })
        else:
            event_key = (event, date)
            if event_key not in events:
                events[event_key] = []
            
            # Get rankings from cache or calculate if not available
            ranking_key = (event, date, athlete)
            rankings = rankings_dict.get(ranking_key, {})
            
            events[event_key].append({
                'athlete': athlete,
                'result': result,
                'team': team,
                'is_pr': is_pr(athlete, event, result),
                'ranking_before': rankings.get('ranking_before'),
                'ranking_after': rankings.get('ranking_after')
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

    # Get comments for this meet
    comments = Comment.get_comments('meet', meet_name)
    comment_count = Comment.get_comment_count('meet', meet_name)

    return render_template('meet.html', 
                         meet_name=meet_name, 
                         events=events, 
                         team_logos=team_logos, 
                         form=form, 
                         sorted_teams=sorted_teams,
                         comment_form=comment_form,
                         comments=comments,
                         comment_count=comment_count)

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

@meet_bp.route('/meet/<meet_name>/calculate_rankings', methods=['POST'])
def calculate_rankings(meet_name):
    """Calculate and cache rankings for all athletes in a meet"""
    # Get all results for this meet
    raw_results = Result.get_meet_results(meet_name)
    
    # Group results by event and date
    events_by_date = {}
    for row in raw_results:
        date, athlete, event, result, team = row
        event_date_key = (event, date)
        if event_date_key not in events_by_date:
            events_by_date[event_date_key] = []
        events_by_date[event_date_key].append({
            'athlete': athlete,
            'result': result,
            'team': team
        })
    
    # Calculate rankings for each event/date combination
    rankings_data = []
    for (event, date), results in events_by_date.items():
        # Skip relay splits as they're part of the relay event
        if event == "400m RS":
            continue
            
        # Calculate rankings before the meet (excluding current results)
        rankings_before = AthleteRanking.calculate_rankings_for_date(event, date, include_current=False)
        
        # Calculate rankings after the meet (including current results)
        rankings_after = AthleteRanking.calculate_rankings_for_date(event, date, include_current=True)
        
        # Store rankings for each athlete in this event
        for result in results:
            athlete = result['athlete']
            rankings_data.append({
                'event': event,
                'date': date,
                'athlete': athlete,
                'ranking_before': rankings_before.get(athlete),
                'ranking_after': rankings_after.get(athlete)
            })
    
    # Cache the calculated rankings
    AthleteRanking.update_meet_rankings(meet_name, rankings_data)
    
    flash('Athlete rankings have been calculated and cached!', 'success')
    return redirect(url_for('meet.meet_results', meet_name=meet_name)) 

 