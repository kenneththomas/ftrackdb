from flask import Blueprint, render_template, request, jsonify
from models import Result, Database, Athlete
from forms import SearchForm
from utils.relay_utils import calculate_relay_results

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
        prs = {event: prs[event] for event in preforder if event in prs}
    if annual_prs:
        annual_prs = {event: annual_prs[event] for event in preforder if event in annual_prs}
    
    # Get team and class with defaults
    team = athlete_info.get('Team', 'Unknown')
    athlete_class = athlete_info.get('Class', 'Unknown')
    
    # Get gender flag for athlete from Athletes table
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT is_female FROM Athletes WHERE athlete_name = ?', (name,))
        gender_row = cur.fetchone()
        is_female = bool(gender_row[0]) if gender_row and gender_row[0] is not None else False
    
    # ---------------------------
    # Compute relay results for the athlete
    relay_results = []
    relay_types = ['200m RS', '400m RS', '800m RS']
    
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
    
    return render_template('profile.html', 
                         name=name, 
                         results=results, 
                         prs=prs,
                         annual_prs=annual_prs,
                         team=team, 
                         athlete_class=athlete_class,
                         bio=bio,
                         relay_results=relay_results,
                         is_female=is_female)

@athlete_bp.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    if form.validate_on_submit():
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            
            cur.execute('SELECT Date, Athlete, Event, Result, Team FROM Results WHERE Athlete LIKE ? ORDER BY Date DESC', 
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