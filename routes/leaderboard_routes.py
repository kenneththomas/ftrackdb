from flask import Blueprint, render_template, request, redirect, url_for
from models import Database, Team
from utils.relay_utils import calculate_relay_results, parse_time
from utils.field_utils import parse_field_result, all_results_are_field_format
from collections import defaultdict
from datetime import datetime, timedelta

# Create blueprint
leaderboard_bp = Blueprint('leaderboard', __name__)

def is_time_event(event):
    """Check if an event is time-based (lower is better)"""
    return 'm' in event or 'Mile' in event

@leaderboard_bp.route('/leaderboard')
def leaderboard():
    # Get filter parameters
    selected_event = request.args.get('event', '')
    year_filter = request.args.get('year', 'all')
    best_only = request.args.get('best_only', 'true') == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    # Calculate date range for last year if requested
    date_filter = None
    if year_filter == 'last_year':
        today = datetime.now()
        one_year_ago = today - timedelta(days=365)
        date_filter = one_year_ago.strftime('%Y-%m-%d')
    
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        
        # Get all distinct events for the dropdown
        cur.execute('''
            SELECT DISTINCT Event 
            FROM Results 
            WHERE Event NOT LIKE '% RS'
            ORDER BY Event ASC
        ''')
        all_events = [row[0] for row in cur.fetchall()]
        
        # Get relay events
        cur.execute('''
            SELECT DISTINCT Event
            FROM Results 
            WHERE Event LIKE '% RS'
        ''')
        relay_events_raw = [row[0] for row in cur.fetchall()]
        relay_events = [f"4x{event.replace(' RS', '')}" for event in relay_events_raw]
        
        # Combine all events
        all_events.extend(relay_events)
        all_events.sort(key=lambda x: (not x.startswith('4x'), x))
        
        results = []
        total_results = 0
        total_pages = 0
        is_relay = False
        team_logos = {}
        event_name = selected_event if selected_event else None
        
        if selected_event:
            is_relay = selected_event.startswith('4x')
            
            if is_relay:
                # Handle relay events
                query = '''
                    SELECT Date, Meet_Name, Team, Athlete, Result
                    FROM Results 
                    WHERE Event = ?
                '''
                params = [selected_event.replace('4x', '') + ' RS']
                
                if date_filter:
                    query += ' AND Date >= ?'
                    params.append(date_filter)
                    
                query += ' ORDER BY Date DESC'
                
                cur.execute(query, params)
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
                        relay_result = calculate_relay_results(splits, selected_event.replace('4x', '') + ' RS')
                        if relay_result:
                            relay_results.extend(relay_result)
                
                # Sort relay results by time
                relay_results.sort(key=lambda x: parse_time(x['result']))
                
                # If best_only, keep only best result per team
                if best_only:
                    team_best = {}
                    for r in relay_results:
                        team = r['team']
                        if team not in team_best or parse_time(r['result']) < parse_time(team_best[team]['result']):
                            team_best[team] = r
                    relay_results = list(team_best.values())
                    relay_results.sort(key=lambda x: parse_time(x['result']))
                
                # Get team logos
                teams = set(r['team'] for r in relay_results)
                for team in teams:
                    team_info = Team.get_team_info(team)
                    if team_info and team_info.get('logo_url'):
                        team_logos[team] = team_info['logo_url']
                
                total_results = len(relay_results)
                total_pages = (total_results + per_page - 1) // per_page
                results = relay_results[offset:offset + per_page]
            else:
                # Handle non-relay events
                if best_only:
                    # Get best result per athlete
                    if is_time_event(selected_event):
                        # Time events: lower is better
                        query = '''
                            WITH BestResults AS (
                                SELECT 
                                    Athlete,
                                    Result,
                                    Team,
                                    Date,
                                    Meet_Name,
                                    CASE 
                                        WHEN Result LIKE '%:%' THEN
                                            CAST(SUBSTR(Result, 1, INSTR(Result, ':') - 1) AS REAL) * 60 +
                                            CAST(SUBSTR(Result, INSTR(Result, ':') + 1) AS REAL)
                                        ELSE
                                            CAST(Result AS REAL)
                                    END as numeric_result
                                FROM Results 
                                WHERE Event = ?
                        '''
                        params = [selected_event]
                        
                        if date_filter:
                            query += ' AND Date >= ?'
                            params.append(date_filter)
                        
                        query += '''
                            ),
                            AthletePRs AS (
                                SELECT 
                                    Athlete,
                                    MIN(numeric_result) as best_result
                                FROM BestResults
                                GROUP BY Athlete
                            ),
                            RankedResults AS (
                                SELECT 
                                    br.Athlete,
                                    br.Result,
                                    br.Team,
                                    br.Date,
                                    br.Meet_Name,
                                    pr.best_result,
                                    ROW_NUMBER() OVER (PARTITION BY br.Athlete ORDER BY br.Date DESC) as rn
                                FROM BestResults br
                                INNER JOIN AthletePRs pr ON br.Athlete = pr.Athlete 
                                    AND br.numeric_result = pr.best_result
                            )
                            SELECT 
                                Athlete,
                                Result,
                                Team,
                                Date,
                                Meet_Name
                            FROM RankedResults
                            WHERE rn = 1
                            ORDER BY best_result ASC
                            LIMIT ? OFFSET ?
                        '''
                        params.extend([per_page, offset])
                        
                        cur.execute(query, params)
                        results = cur.fetchall()
                        
                        # Get total count
                        count_query = '''
                            WITH BestResults AS (
                                SELECT 
                                    Athlete,
                                    CASE 
                                        WHEN Result LIKE '%:%' THEN
                                            CAST(SUBSTR(Result, 1, INSTR(Result, ':') - 1) AS REAL) * 60 +
                                            CAST(SUBSTR(Result, INSTR(Result, ':') + 1) AS REAL)
                                        ELSE
                                            CAST(Result AS REAL)
                                    END as numeric_result
                                FROM Results 
                                WHERE Event = ?
                        '''
                        count_params = [selected_event]
                        
                        if date_filter:
                            count_query += ' AND Date >= ?'
                            count_params.append(date_filter)
                        
                        count_query += '''
                            )
                            SELECT COUNT(DISTINCT Athlete) 
                            FROM BestResults
                        '''
                        cur.execute(count_query, count_params)
                        total_results = cur.fetchone()[0]
                    else:
                        # Field events: higher is better. May be decimal or ft-in (e.g. 20'0").
                        fetch_params = [selected_event]
                        fetch_query = 'SELECT Athlete, Result, Team, Date, Meet_Name FROM Results WHERE Event = ?'
                        if date_filter:
                            fetch_query += ' AND Date >= ?'
                            fetch_params.append(date_filter)
                        cur.execute(fetch_query, fetch_params)
                        all_field_rows = cur.fetchall()
                        result_strs = [r[1] for r in all_field_rows]

                        if all_results_are_field_format(result_strs):
                            # Ft-in format: sort by parse_field_result (higher = better) in Python
                            if best_only:
                                by_athlete = defaultdict(list)
                                for row in all_field_rows:
                                    by_athlete[row[0]].append(row)
                                best_per_athlete = [max(rows, key=lambda r: parse_field_result(r[1])) for rows in by_athlete.values()]
                                best_per_athlete.sort(key=lambda r: parse_field_result(r[1]), reverse=True)
                                total_results = len(best_per_athlete)
                                results = best_per_athlete[offset:offset + per_page]
                            else:
                                all_field_rows.sort(key=lambda r: parse_field_result(r[1]), reverse=True)
                                total_results = len(all_field_rows)
                                results = all_field_rows[offset:offset + per_page]
                            total_pages = (total_results + per_page - 1) // per_page
                        else:
                            # Decimal field (e.g. meters): use SQL
                            query = '''
                                WITH BestResults AS (
                                    SELECT 
                                        Athlete,
                                        Result,
                                        Team,
                                        Date,
                                        Meet_Name,
                                        CAST(Result AS REAL) as numeric_result
                                    FROM Results 
                                    WHERE Event = ?
                                        AND Result GLOB '[0-9]*.[0-9]*'
                            '''
                            params = [selected_event]
                            if date_filter:
                                query += ' AND Date >= ?'
                                params.append(date_filter)
                            query += '''
                                ),
                                AthletePRs AS (
                                    SELECT Athlete, MAX(numeric_result) as best_result
                                    FROM BestResults GROUP BY Athlete
                                ),
                                RankedResults AS (
                                    SELECT br.Athlete, br.Result, br.Team, br.Date, br.Meet_Name, pr.best_result,
                                    ROW_NUMBER() OVER (PARTITION BY br.Athlete ORDER BY br.Date DESC) as rn
                                    FROM BestResults br
                                    INNER JOIN AthletePRs pr ON br.Athlete = pr.Athlete AND br.numeric_result = pr.best_result
                                )
                                SELECT Athlete, Result, Team, Date, Meet_Name
                                FROM RankedResults WHERE rn = 1
                                ORDER BY best_result DESC
                                LIMIT ? OFFSET ?
                            '''
                            params.extend([per_page, offset])
                            cur.execute(query, params)
                            results = cur.fetchall()
                            count_query = '''
                                WITH BestResults AS (
                                    SELECT Athlete, CAST(Result AS REAL) as numeric_result
                                    FROM Results WHERE Event = ? AND Result GLOB '[0-9]*.[0-9]*'
                            '''
                            count_params = [selected_event]
                            if date_filter:
                                count_query += ' AND Date >= ?'
                                count_params.append(date_filter)
                            count_query += ') SELECT COUNT(DISTINCT Athlete) FROM BestResults'
                            cur.execute(count_query, count_params)
                            total_results = cur.fetchone()[0]
                            total_pages = (total_results + per_page - 1) // per_page
                else:
                    # Get all performances
                    query = '''
                        SELECT Athlete, Result, Team, Date, Meet_Name
                        FROM Results 
                        WHERE Event = ?
                    '''
                    params = [selected_event]
                    if date_filter:
                        query += ' AND Date >= ?'
                        params.append(date_filter)

                    if is_time_event(selected_event):
                        query += '''
                            ORDER BY 
                                CASE 
                                    WHEN Result LIKE '%:%' THEN
                                        CAST(SUBSTR(Result, 1, INSTR(Result, ':') - 1) AS REAL) * 60 +
                                        CAST(SUBSTR(Result, INSTR(Result, ':') + 1) AS REAL)
                                    ELSE
                                        CAST(Result AS REAL)
                                END ASC
                        '''
                        query += ' LIMIT ? OFFSET ?'
                        params.extend([per_page, offset])
                        cur.execute(query, params)
                        results = cur.fetchall()
                        count_query = 'SELECT COUNT(*) FROM Results WHERE Event = ?'
                        count_params = [selected_event]
                        if date_filter:
                            count_query += ' AND Date >= ?'
                            count_params.append(date_filter)
                        cur.execute(count_query, count_params)
                        total_results = cur.fetchone()[0]
                        total_pages = (total_results + per_page - 1) // per_page
                    else:
                        # Field: may be ft-in or decimal
                        cur.execute(query, params)
                        all_field_rows = cur.fetchall()
                        result_strs = [r[1] for r in all_field_rows]
                        if all_results_are_field_format(result_strs):
                            all_field_rows.sort(key=lambda r: parse_field_result(r[1]), reverse=True)
                            total_results = len(all_field_rows)
                            total_pages = (total_results + per_page - 1) // per_page
                            results = all_field_rows[offset:offset + per_page]
                        else:
                            query += ' ORDER BY CAST(Result AS REAL) DESC'
                            query += ' LIMIT ? OFFSET ?'
                            params.extend([per_page, offset])
                            cur.execute(query, params)
                            results = cur.fetchall()
                            count_query = 'SELECT COUNT(*) FROM Results WHERE Event = ?'
                            count_params = [selected_event]
                            if date_filter:
                                count_query += ' AND Date >= ?'
                                count_params.append(date_filter)
                            cur.execute(count_query, count_params)
                            total_results = cur.fetchone()[0]
                            total_pages = (total_results + per_page - 1) // per_page
        
    return render_template('leaderboard.html',
                        all_events=all_events,
                        selected_event=selected_event,
                        results=results,
                        page=page,
                        per_page=per_page,
                        total_pages=total_pages,
                        year_filter=year_filter,
                        best_only=best_only,
                        is_relay=is_relay,
                        team_logos=team_logos,
                        event_name=event_name)

@leaderboard_bp.route('/leaderboard/<event>')
def event_leaderboard_redirect(event):
    """Redirect old event-specific leaderboard URLs to the unified leaderboard"""
    year = request.args.get('year', 'all')
    page = request.args.get('page', 1)
    # Default to best_only=true for backward compatibility
    return redirect(url_for('leaderboard.leaderboard', event=event, year=year, page=page, best_only='true')) 