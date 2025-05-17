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
    
    results = Result.get_recent_results(limit=per_page, offset=(page-1)*per_page)
    total_results = Result.get_total_results()
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5006)