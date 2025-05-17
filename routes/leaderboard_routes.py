from flask import Blueprint, render_template, request
from models import Database

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
    return render_template('leaderboard.html', event_data=event_data)

@leaderboard_bp.route('/leaderboard/<event>')
def event_leaderboard(event):
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # Get total count for pagination
        cur.execute('SELECT COUNT(DISTINCT Athlete) FROM Results WHERE Event = ?', (event,))
        total_results = cur.fetchone()[0]
        
        # Get paginated results
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
                         total_pages=total_pages) 