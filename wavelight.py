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

# Add a custom Jinja filter to convert Markdown to HTML
app.jinja_env.filters['markdown_to_html'] = markdown_to_html

@app.route('/')
def home():
    form = SearchForm()
    page = request.args.get('page', 1, type=int)
    per_page = 25  # Number of results per page
    
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
    page = request.args.get('page', 1, type=int)
    per_page = 25
    search = request.args.get('search', '', type=str)
    offset = (page - 1) * per_page
    results = Result.get_recent_meets(limit=per_page, offset=offset, search=search if search else None)
    total_results = Result.get_total_meets(search=search if search else None)
    total_pages = (total_results + per_page - 1) // per_page
    return render_template('meets.html', results=results, page=page, total_pages=total_pages, search=search)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5006)