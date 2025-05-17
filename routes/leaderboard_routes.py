from flask import Blueprint, render_template, request
from models import Database, Team
from utils.relay_utils import calculate_relay_results, parse_time

# Create blueprint
leaderboard_bp = Blueprint('leaderboard', __name__)

@leaderboard_bp.route('/leaderboard')
def leaderboard():
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # Get all distinct events and count of results for each event
        cur.execute('''
            SELECT Event, COUNT(DISTINCT Athlete) as athlete_count 
            FROM Results 
            GROUP BY Event 
            ORDER BY Event ASC
        ''')
        event_data = cur.fetchall()
        
        # Get relay events
        cur.execute('''
            SELECT DISTINCT Event
            FROM Results 
            WHERE Event LIKE '% RS'
        ''')
        relay_events = [row[0] for row in cur.fetchall()]
        
        # Convert relay events to 4x format
        relay_events_4x = [f"4x{event.replace(' RS', '')}" for event in relay_events]
        
        # Add relay events to event_data
        for relay_event in relay_events_4x:
            # Count number of teams that have completed this relay
            cur.execute('''
                WITH RelayTeams AS (
                    SELECT Team, Date, Meet_Name
                    FROM Results 
                    WHERE Event = ?
                    GROUP BY Team, Date, Meet_Name
                    HAVING COUNT(DISTINCT Athlete) >= 4
                )
                SELECT COUNT(*) FROM RelayTeams
            ''', (relay_event.replace('4x', '') + ' RS',))
            team_count = cur.fetchone()[0]
            event_data.append((relay_event, team_count))
        
        # Sort event_data to keep relays together
        event_data.sort(key=lambda x: (not x[0].startswith('4x'), x[0]))
        
    return render_template('leaderboard.html', event_data=event_data)

@leaderboard_bp.route('/leaderboard/<event>')
def event_leaderboard(event):
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        
        # Check if this is a relay event
        is_relay = event.startswith('4x') or event.endswith(' RS')
        
        if is_relay:
            # For relay events, we need to handle them differently
            # First get all relay splits
            cur.execute('''
                SELECT Date, Meet_Name, Team, Athlete, Result
                FROM Results 
                WHERE Event = ?
                ORDER BY Date DESC
            ''', (event.replace('4x', '') + ' RS',))
            relay_splits = cur.fetchall()
            
            # Group splits by team and date
            relay_by_team = {}
            for date, meet, team, athlete, result in relay_splits:
                key = (team, date, meet)
                if key not in relay_by_team:
                    relay_by_team[key] = []
                relay_by_team[key].append((athlete, result, date, meet, team))
            
            # Calculate relay results
            relay_results = []
            for (team, date, meet), splits in relay_by_team.items():
                if len(splits) >= 4:
                    relay_result = calculate_relay_results(splits, event.replace('4x', '') + ' RS')
                    if relay_result:
                        relay_results.extend(relay_result)
            
            # Sort relay results by time
            relay_results.sort(key=lambda x: parse_time(x['result']))
            
            # Get team logos
            teams = set(r['team'] for r in relay_results)
            team_logos = {}
            for team in teams:
                team_info = Team.get_team_info(team)
                if team_info and team_info.get('logo_url'):
                    team_logos[team] = team_info['logo_url']
            
            # Paginate relay results
            total_results = len(relay_results)
            total_pages = (total_results + per_page - 1) // per_page
            paginated_results = relay_results[offset:offset + per_page]
            
            return render_template('event_leaderboard.html',
                                event=event,
                                results=paginated_results,
                                page=page,
                                total_pages=total_pages,
                                is_relay=True,
                                team_logos=team_logos)
        else:
            # For non-relay events, use the original logic
            cur.execute('SELECT COUNT(DISTINCT Athlete) FROM Results WHERE Event = ?', (event,))
            total_results = cur.fetchone()[0]
            
            cur.execute('''
                SELECT Event, Athlete, Result, Team 
                FROM Results 
                WHERE Event = ? 
                GROUP BY Athlete 
                ORDER BY 
                    CASE 
                        WHEN Event = '100m' THEN CAST(Result AS FLOAT)
                        ELSE Result 
                    END ASC
                LIMIT ? OFFSET ?
            ''', (event, per_page, offset))
            results = cur.fetchall()
            
            total_pages = (total_results + per_page - 1) // per_page
            
            return render_template('event_leaderboard.html', 
                                event=event,
                                results=results,
                                page=page,
                                total_pages=total_pages,
                                is_relay=False) 