import os
from flask import Blueprint, render_template, request, jsonify, url_for
from models import Result, Database, Athlete, Team, AthleteRanking, StaggerScore, BoardPost, RelayTeam
from forms import SearchForm, BoardPostForm, BoardGenerateForm
from utils.relay_utils import calculate_relay_results, explicit_relay_to_display_dict

# Create blueprint
athlete_bp = Blueprint('athlete', __name__)

@athlete_bp.route('/athlete/<name>')
def athlete_profile(name):
    results, prs, athlete_info, bio = Result.get_athlete_results(name)
    
    # preferred order of events
    preforder = ['60m', '100m', '100mH', '110mH', '200m', '300m', '400m', '400m RS', '400mH',
                '500m', '600yd', '600m', '800m', '1000m', '1500m', 'Mile',
                '3000m', '3200m', '5000m', '5K XC', '5K Road', '10000m',
                'Half Marathon', 'Marathon', 'High Jump', 'Long Jump',
                'Triple Jump', 'Shot Put', 'Discus', 'Pole Vault', 'Javelin', '4x400m']
    
    # Get annual PRs (last 365 days)
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('''
            WITH RankedResults AS (
                SELECT 
                    Event,
                    Result,
                    ROW_NUMBER() OVER (PARTITION BY Event ORDER BY 
                        CASE 
                            WHEN Event IN ('100m', '200m', '400m', '800m', '1500m', '3000m', '5000m', '10000m') 
                            THEN CAST(REPLACE(Result, ':', '') AS DECIMAL)
                            ELSE Result 
                        END ASC) as rn
                FROM Results 
                WHERE Athlete = ? 
                AND Date >= date('now', '-365 days')
            )
            SELECT Event, Result
            FROM RankedResults
            WHERE rn = 1
            ORDER BY Event
        ''', (name,))
        annual_prs = dict(cur.fetchall())
    
    # sort prs by preferred order (handle empty prs)
    if prs:
        sorted_prs = {}
        for event in preforder:
            if event in prs:
                sorted_prs[event] = prs[event]
        prs = sorted_prs
    if annual_prs:
        annual_prs = {event: annual_prs[event] for event in preforder if event in annual_prs}
    
    # Get team and class with defaults
    team = athlete_info.get('Team', 'Unknown')
    athlete_class = athlete_info.get('Class', 'Unknown')
    
    # Get team logo for current team
    team_logo = None
    if team != 'Unknown':
        team_info = Team.get_team_info(team)
        if team_info and team_info.get('logo_url'):
            team_logo = team_info['logo_url']
    
    # Get team logos for all teams in results
    team_logos = {}
    teams = set()
    for result in results:
        if result and len(result) > 4:
            teams.add(result[4])
    
    for team_name in teams:
        team_info = Team.get_team_info(team_name)
        if team_info and team_info.get('logo_url'):
            team_logos[team_name] = team_info['logo_url']
    
    # Get gender flag for athlete from Athletes table
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT is_female FROM Athletes WHERE athlete_name = ?', (name,))
        gender_row = cur.fetchone()
        is_female = bool(gender_row[0]) if gender_row and gender_row[0] is not None else False
    
    # ---------------------------
    # Compute relay results for the athlete
    relay_results = []
    relay_types = ['100m RS', '200m RS', '400m RS', '800m RS']
    
    with conn:
        cur = conn.cursor()
        for relay_type in relay_types:
            cur.execute("""
                SELECT DISTINCT Date, Meet_Name, Team 
                FROM Results 
                WHERE Event = ? AND Athlete = ?
            """, (relay_type, name))
            relay_keys = cur.fetchall()
            
            for date, meet, team in relay_keys:
                cur.execute("""
                    SELECT Athlete, Result, Date, Meet_Name, Team
                    FROM Results 
                    WHERE Event = ? AND Date=? AND Meet_Name=? AND Team=?
                """, (relay_type, date, meet, team))
                splits = cur.fetchall()
                if splits:
                    relay_results.extend(calculate_relay_results(splits, relay_type))
    
    # Add explicit relay results from RelayTeams/RelayLegs
    explicit_relays = RelayTeam.get_relays_for_athlete(name)
    for relay in explicit_relays:
        relay_results.append(explicit_relay_to_display_dict(relay))
    
    # Get current rankings for the athlete
    rankings = AthleteRanking.calculate_athlete_rankings(name)
    
    # Stagger scores per event (for display near PRs)
    stagger_scores = StaggerScore.get_scores_for_athlete(name)

    # Stagger delta by meet for this athlete: (meet_name, event, date) -> delta
    with conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT meet_name, event, date, delta
            FROM StaggerHistory
            WHERE athlete = ?
        ''', (name,))
        stagger_deltas = {(row[0], row[1], row[2]): float(row[3]) for row in cur.fetchall()}
    
    # Create a set of PR results for quick lookup (normalize for comparison)
    def normalize_result(result_str):
        """Normalize result string for comparison"""
        if not result_str:
            return None
        # Remove leading/trailing whitespace
        result_str = result_str.strip()
        # For times with colons, keep as is for now
        return result_str
    
    # Create a mapping of (event, normalized_result) -> True for PRs
    pr_results_set = set()
    for event, pr_data in prs.items():
        if isinstance(pr_data, dict):
            pr_result = pr_data.get('result', '')
        else:
            pr_result = pr_data
        if pr_result:
            normalized = normalize_result(str(pr_result))
            if normalized:
                pr_results_set.add((event, normalized))
    
    # Pre-process results to mark which ones are PRs
    results_with_pr_flag = []
    for result in results:
        try:
            if not result:
                continue
            try:
                event = result[2]
                result_value = result[3]
            except (IndexError, TypeError):
                continue
            normalized = normalize_result(result_value)
            is_pr = normalized and (event, normalized) in pr_results_set
            date_str = str(result[0]) if result[0] else ''
            date_key = date_str[:10] if date_str and len(date_str) >= 10 else date_str
            delta = stagger_deltas.get((result[1], event, date_key))
            results_with_pr_flag.append((*result, is_pr, delta))
        except Exception as e:
            continue
    
    board_posts = BoardPost.get_threaded_posts(page_type='athlete', page_id=name)
    openrouter_available = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    
    return render_template('profile.html', 
                         name=name, 
                         results=results_with_pr_flag, 
                         prs=prs,
                         annual_prs=annual_prs,
                         team=team, 
                         athlete_class=athlete_class,
                         bio=bio,
                         relay_results=relay_results,
                         is_female=is_female,
                         team_logo=team_logo,
                         team_logos=team_logos,
                         rankings=rankings,
                         stagger_scores=stagger_scores,
                         board_posts=board_posts,
                         post_form=BoardPostForm(),
                         generate_form=BoardGenerateForm(),
                         openrouter_available=openrouter_available,
                         post_action_url=url_for('board.athlete_board_post', name=name),
                         generate_action_url=url_for('board.athlete_board_generate', name=name),
                         section_title='Discussion')

@athlete_bp.route('/athlete/<name>/calculate_rankings', methods=['POST'])
def calculate_athlete_rankings(name):
    """Calculate and return current rankings for an athlete"""
    rankings = AthleteRanking.calculate_athlete_rankings(name)
    return jsonify({'success': True, 'rankings': rankings})

@athlete_bp.route('/get_athlete_bests_since/<name>')
def get_athlete_bests_since(name):
    """Get best results for each event since a given date"""
    since_date = request.args.get('since', '')
    if not since_date:
        return jsonify({'success': False, 'error': 'Missing since date'}), 400
    
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT Event, Result, Date
            FROM Results
            WHERE Athlete = ? AND Date >= ?
            ORDER BY Event, Date
        ''', (name, since_date))
        rows = cur.fetchall()
    
    # Find best result for each event using numeric comparison
    event_results = {}
    for row in rows:
        event = row[0]
        if event not in event_results:
            event_results[event] = []
        event_results[event].append((row[1], row[2]))
    
    bests = []
    for event, results in event_results.items():
        best_result = None
        best_date = None
        for result_str, date in results:
            if not result_str:
                continue
            try:
                if ':' in result_str:
                    parts = result_str.split(':')
                    numeric = float(parts[0]) * 60 + float(parts[1])
                else:
                    numeric = float(result_str)
                
                if best_result is None:
                    best_result = result_str
                    best_date = date
                elif 'm' in event or 'H' in event or 'XC' in event or 'Road' in event or 'Marathon' in event:
                    if numeric < float(best_result.split(':')[0]) * 60 + float(best_result.split(':')[1]) if ':' in best_result else float(best_result):
                        best_result = result_str
                        best_date = date
                else:
                    if numeric > float(best_result):
                        best_result = result_str
                        best_date = date
            except (ValueError, IndexError):
                if best_result is None:
                    best_result = result_str
                    best_date = date
        
        if best_result:
            bests.append({'event': event, 'result': best_result, 'date': best_date})
    
    return jsonify({'success': True, 'bests': bests})

@athlete_bp.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    if form.validate_on_submit():
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            
            cur.execute('SELECT Date, Athlete, Meet_Name, Event, Result, Team FROM Results WHERE Athlete LIKE ? ORDER BY Date DESC', 
                       ('%' + form.athlete.data + '%',))
            results = cur.fetchall()
        return render_template('search.html', form=form, results=results)

    return render_template('search.html', form=form)

@athlete_bp.route('/update_bio/<name>', methods=['POST'])
def update_bio(name):
    try:
        bio = request.form.get('bio')
        Athlete.update_bio(name, bio)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@athlete_bp.route('/update_gender/<name>', methods=['POST'])
def update_gender(name):
    try:
        # Accept either form data or JSON data.
        is_female_str = request.form.get('is_female') or (request.json and request.json.get('is_female'))
        # Interpret common representations
        is_female = 1 if str(is_female_str).lower() in ['1', 'true', 'yes'] else 0
        Athlete.update_gender(name, is_female)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@athlete_bp.route('/lookup_team/<athlete_name>')
def lookup_team(athlete_name):
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute(''' 
            SELECT Team 
            FROM Results 
            WHERE Athlete = ? 
            ORDER BY Date DESC 
            LIMIT 1
        ''', (athlete_name,))
        result = cur.fetchone()
    
    if result:
        return jsonify({'team': result[0]})
    else:
        return jsonify({'team': None}) 