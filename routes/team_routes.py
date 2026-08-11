from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Database, Team, StaggerScore
from utils.relay_utils import parse_time
from utils.field_utils import parse_field_result
from utils.leaderboard import is_time_event

# Create blueprint
team_bp = Blueprint('team', __name__)


def _is_time_event(event_name: str) -> bool:
    return is_time_event(event_name)


def get_team_leaderboard_results(cursor, team_name: str, selected_event: str, best_only: bool, page: int = 1, per_page: int = 50):
    """
    Return list of leaderboard dicts for the given team/event/mode.
    Each dict has athlete, result, date, meet, stagger_score (and metric for sorting).
    Returns (results, total_results).
    """
    if not selected_event:
        return [], 0
    StaggerScore.ensure_current()
    cursor.execute(
        '''
        SELECT Results.Athlete, Results.Result, Results.Date, Results.Meet_Name, StaggerScores.score
        FROM Results
        LEFT JOIN StaggerScores
            ON StaggerScores.athlete = Results.Athlete
           AND StaggerScores.event = Results.Event
        WHERE Results.Team = ? AND Results.Event = ?
        ''',
        (team_name, selected_event),
    )
    rows = cursor.fetchall()
    time_based = _is_time_event(selected_event)
    if best_only:
        best_per_athlete = {}
        for athlete, result, date, meet, stagger_score in rows:
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
                    'stagger_score': stagger_score,
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
                        'stagger_score': stagger_score,
                        'metric': metric,
                    }
        sorted_results = sorted(
            best_per_athlete.values(),
            key=lambda r: r['metric'],
            reverse=not time_based,
        )
    else:
        enriched = []
        for athlete, result, date, meet, stagger_score in rows:
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
                'stagger_score': stagger_score,
                'metric': metric,
            })
        sorted_results = sorted(
            enriched,
            key=lambda r: r['metric'],
            reverse=not time_based,
        )
    total_results = len(sorted_results)
    offset = (page - 1) * per_page
    return sorted_results[offset:offset + per_page], total_results


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
        results_page = max(request.args.get('results_page', 1, type=int), 1)
        results_per_page = 50

        cur.execute('SELECT COUNT(*) FROM Results WHERE Team = ?', (team_name,))
        total_team_results = cur.fetchone()[0]
        results_total_pages = (
            (total_team_results + results_per_page - 1) // results_per_page
            if total_team_results
            else 0
        )
        if results_total_pages and results_page > results_total_pages:
            results_page = results_total_pages
        results_offset = (results_page - 1) * results_per_page

        # Get paginated results for this team (for the "All Results" section)
        cur.execute(
            'SELECT Date, Athlete, Meet_Name, Event, Result '
            'FROM Results WHERE Team = ? ORDER BY Date DESC '
            'LIMIT ? OFFSET ?',
            (team_name, results_per_page, results_offset),
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
        page = request.args.get('page', 1, type=int)
        per_page = 50
        if not selected_event and events:
            selected_event = events[0]

        leaderboard_results, total_results = get_team_leaderboard_results(
            cur, team_name, selected_event, best_only, page, per_page
        )
        total_pages = (total_results + per_page - 1) // per_page if total_results else 0

    team_info = Team.get_team_info(team_name)

    return render_template('team.html',
                         team_name=team_name,
                         results=team_results,
                         events=events,
                         selected_event=selected_event,
                         best_only=best_only,
                         leaderboard_results=leaderboard_results,
                         page=page,
                         per_page=per_page,
                         total_pages=total_pages,
                         results_page=results_page,
                         results_per_page=results_per_page,
                         results_total_pages=results_total_pages,
                         total_team_results=total_team_results,
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
        page = request.args.get('page', 1, type=int)
        per_page = 50
        if not selected_event and events:
            selected_event = events[0]

        leaderboard_results, total_results = get_team_leaderboard_results(
            cur, team_name, selected_event, best_only, page, per_page
        )
        total_pages = (total_results + per_page - 1) // per_page if total_results else 0

    return render_template(
        'partials/team_leaderboard_content.html',
        team_name=team_name,
        events=events,
        selected_event=selected_event,
        best_only=best_only,
        leaderboard_results=leaderboard_results,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
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
