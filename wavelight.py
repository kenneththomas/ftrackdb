from dotenv import load_dotenv
load_dotenv()

import calendar
from datetime import date, datetime
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_wtf import CSRFProtect
from forms import ResultForm, SearchForm
from models import Result, Database, Athlete
from utils.template_filters import markdown_to_html

# Import blueprints
from routes.athlete_routes import athlete_bp
from routes.result_routes import result_bp
from routes.team_routes import team_bp
from routes.meet_routes import meet_bp
from routes.leaderboard_routes import leaderboard_bp
from routes.comment_routes import comment_bp
from routes.football_routes import football_bp
from routes.board_routes import board_bp

app = Flask(__name__)
app.config['DATABASE'] = 'track.db'
app.secret_key = 'your_secret_key_here'
csrf = CSRFProtect(app)

# Register blueprints
app.register_blueprint(athlete_bp)
app.register_blueprint(result_bp)
app.register_blueprint(team_bp)
app.register_blueprint(meet_bp)
app.register_blueprint(leaderboard_bp)
app.register_blueprint(comment_bp)
app.register_blueprint(football_bp)
app.register_blueprint(board_bp)

# Exempt API endpoint from CSRF (JSON POST; no form)
if 'result.fill_result_blanks' in app.view_functions:
    csrf.exempt(app.view_functions['result.fill_result_blanks'])

# Add a custom Jinja filter to convert Markdown to HTML
app.jinja_env.filters['markdown_to_html'] = markdown_to_html

@app.route('/')
def home():
    form = SearchForm()
    page = request.args.get('page', 1, type=int)
    per_page = 25  # Number of results per page
    
    # Event filter options
    filter_events = ['100m', '200m', '400m', '800m', '1500m', 'Mile', '3000m', '5000m', '10000m']
    
    # Get team logos for all teams
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    results = Result.get_recent_winners(limit=per_page, offset=(page-1)*per_page)
    total_results = Result.get_total_winners()
    total_pages = (total_results + per_page - 1) // per_page
    
    return render_template('index.html', 
                         results=results, 
                         form=form, 
                         team_logos=team_logos,
                         filter_events=filter_events,
                         page=page,
                         total_pages=total_pages)

@app.context_processor
def inject_get_gender():
    return dict(get_gender=Athlete.get_gender)

@app.route('/get_team_members/<team_name>')
def get_team_members(team_name):
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        if len(team_name) >= 5:
            # Use LIKE for partial matching when query is 5+ characters
            cur.execute('''
                SELECT DISTINCT Athlete 
                FROM Results 
                WHERE Team LIKE ? 
                ORDER BY Athlete
            ''', (f'%{team_name}%',))
        else:
            # Exact match for shorter queries
            cur.execute('''
                SELECT DISTINCT Athlete 
                FROM Results 
                WHERE Team = ? 
                ORDER BY Athlete
            ''', (team_name,))
        members = [row[0] for row in cur.fetchall()]
        return jsonify({'members': members})

@app.route('/get_athlete_prs/<athlete_name>')
def get_athlete_prs(athlete_name):
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT Event, MIN(Result) as PR
            FROM Results 
            WHERE Athlete = ? 
            GROUP BY Event
            ORDER BY Event
        ''', (athlete_name,))
        prs = [{'event': row[0], 'pr': row[1]} for row in cur.fetchall()]
        return jsonify({'prs': prs})

@app.route('/meets')
def meets():
    search = request.args.get('search', '', type=str)
    selected_day = request.args.get('day', '', type=str)
    search_term = search if search else None

    if selected_day:
        try:
            day_date = datetime.strptime(selected_day, '%Y-%m-%d').date()
        except ValueError:
            return redirect(url_for('meets', search=search))

        results = Result.get_meets_for_date(selected_day, search=search_term)
        return render_template(
            'meets.html',
            view_mode='day',
            results=results,
            search=search,
            selected_day=day_date,
            month=day_date.month,
            year=day_date.year,
        )

    latest_meet_date = Result.get_latest_meet_date(search=search_term)
    today = date.today()
    default_year = today.year
    default_month = today.month
    if latest_meet_date:
        latest_date = datetime.strptime(latest_meet_date, '%Y-%m-%d').date()
        default_year = latest_date.year
        default_month = latest_date.month

    year = request.args.get('year', default_year, type=int)
    month = request.args.get('month', default_month, type=int)
    if month < 1 or month > 12 or year < 1900 or year > 2200:
        return redirect(url_for('meets', year=default_year, month=default_month, search=search))

    month_start = date(year, month, 1)
    previous_month = month_start.replace(year=year - 1, month=12) if month == 1 else month_start.replace(month=month - 1)
    next_month = month_start.replace(year=year + 1, month=1) if month == 12 else month_start.replace(month=month + 1)

    month_meets = Result.get_meets_for_month(year, month, search=search_term)
    meets_by_day = {}
    for meet_name, meet_date in month_meets:
        meets_by_day.setdefault(meet_date, []).append({'name': meet_name, 'date': meet_date})

    calendar.setfirstweekday(calendar.SUNDAY)
    calendar_weeks = []
    for week in calendar.monthcalendar(year, month):
        calendar_weeks.append([
            {
                'day': day_number,
                'date': date(year, month, day_number).strftime('%Y-%m-%d') if day_number else '',
                'meets': meets_by_day.get(date(year, month, day_number).strftime('%Y-%m-%d'), []) if day_number else [],
            }
            for day_number in week
        ])

    return render_template(
        'meets.html',
        view_mode='calendar',
        calendar_weeks=calendar_weeks,
        month=month,
        year=year,
        month_name=calendar.month_name[month],
        previous_month=previous_month,
        next_month=next_month,
        search=search,
        total_meets=len(month_meets),
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5006)
