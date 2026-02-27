from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Database, Team
from utils.relay_utils import parse_time
from utils.field_utils import parse_field_result

# Create blueprint
team_bp = Blueprint('team', __name__)


def _is_time_event(event_name: str) -> bool:
    """Return True if this looks like a time-based track event."""
    return 'm' in event_name or 'Mile' in event_name


def get_team_leaderboard_results(cursor, team_name: str, selected_event: str, best_only: bool):
    """
    Return list of leaderboard dicts for the given team/event/mode.
    Each dict has athlete, result, date, meet (and metric for sorting).
    """
    if not selected_event:
        return []
    cursor.execute(
        '''
        SELECT Athlete, Result, Date, Meet_Name
        FROM Results
        WHERE Team = ? AND Event = ?
        ''',
        (team_name, selected_event),
    )
    rows = cursor.fetchall()
    time_based = _is_time_event(selected_event)
    if best_only:
        best_per_athlete = {}
        for athlete, result, date, meet in rows:
            if not result:
                continue
            metric = (
                parse_time(result) if time_based else parse_field_result(result)
            )
            existing = best_per_athlete.get(athlete)
            if existing is None:
                best_per_athlete[athlete] = {
                    'athlete': athlete,
                    'result': result,
                    'date': date,
                    'meet': meet,
                    'metric': metric,
                }
            else:
                better = (
                    metric < existing['metric']
                    if time_based
                    else metric > existing['metric']
                )
                if better:
                    best_per_athlete[athlete] = {
                        'athlete': athlete,
                        'result': result,
                        'date': date,
                        'meet': meet,
                        'metric': metric,
                    }
        return sorted(
            best_per_athlete.values(),
            key=lambda r: r['metric'],
            reverse=not time_based,
        )
    enriched = []
    for athlete, result, date, meet in rows:
        if not result:
            continue
        metric = (
            parse_time(result) if time_based else parse_field_result(result)
        )
        enriched.append({
            'athlete': athlete,
            'result': result,
            'date': date,
            'meet': meet,
            'metric': metric,
        })
    return sorted(
        enriched,
        key=lambda r: r['metric'],
        reverse=not time_based,
    )


@team_bp.route('/teams')
def teams():
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # Get all teams with their athlete and result counts
        cur.execute('''
            SELECT 
                Team,
                COUNT(DISTINCT Athlete) as athlete_count,
                COUNT(*) as result_count
            FROM Results 
            GROUP BY Team 
            ORDER BY Team ASC
        ''')
        teams = cur.fetchall()
        # Get team logos for display
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    return render_template('teams.html', teams=teams, team_logos=team_logos)

@team_bp.route('/team/<team_name>')
def team_results(team_name):
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # Get all results for this team (for the "All Results" section)
        cur.execute(
            'SELECT Date, Athlete, Meet_Name, Event, Result '
            'FROM Results WHERE Team = ? ORDER BY Date DESC',
            (team_name,),
        )
        team_results = cur.fetchall()

        # Build list of events this team has results in (exclude relay split rows)
        cur.execute(
            '''
            SELECT DISTINCT Event
            FROM Results
            WHERE Team = ?
              AND Event NOT LIKE '% RS'
            ORDER BY Event ASC
            ''',
            (team_name,),
        )
        events = [row[0] for row in cur.fetchall()]

        selected_event = request.args.get('event', '')
        best_only = request.args.get('best_only', 'true') == 'true'
        if not selected_event and events:
            selected_event = events[0]

        leaderboard_results = get_team_leaderboard_results(
            cur, team_name, selected_event, best_only
        )

    team_info = Team.get_team_info(team_name)

    return render_template('team.html',
                         team_name=team_name,
                         results=team_results,
                         events=events,
                         selected_event=selected_event,
                         best_only=best_only,
                         leaderboard_results=leaderboard_results,
                         team_info=team_info)


@team_bp.route('/team/<team_name>/leaderboard')
def team_leaderboard(team_name):
    """Return HTML fragment of the leaderboard table/empty state for AJAX."""
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT DISTINCT Event
            FROM Results
            WHERE Team = ?
              AND Event NOT LIKE '% RS'
            ORDER BY Event ASC
            ''',
            (team_name,),
        )
        events = [row[0] for row in cur.fetchall()]

        selected_event = request.args.get('event', '')
        best_only = request.args.get('best_only', 'true') == 'true'
        if not selected_event and events:
            selected_event = events[0]

        leaderboard_results = get_team_leaderboard_results(
            cur, team_name, selected_event, best_only
        )

    return render_template(
        'partials/team_leaderboard_content.html',
        team_name=team_name,
        events=events,
        selected_event=selected_event,
        best_only=best_only,
        leaderboard_results=leaderboard_results,
    )

@team_bp.route('/team/<team_name>/update_logo', methods=['POST'])
def update_team_logo(team_name):
    logo_url = request.form.get('logo_url')
    if logo_url:
        Team.update_team_logo(team_name, logo_url)
        flash('Team logo updated successfully!', 'success')
    else:
        flash('No logo URL provided.', 'error')
    return redirect(url_for('team.team_results', team_name=team_name)) 