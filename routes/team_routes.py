from flask import Blueprint, render_template
from models import Database

# Create blueprint
team_bp = Blueprint('team', __name__)

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
    
    return render_template('teams.html', teams=teams)

@team_bp.route('/team/<team_name>')
def team_results(team_name):
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        # Get team results
        cur.execute('SELECT Date, Athlete, Meet_Name, Event, Result FROM Results WHERE Team = ? ORDER BY Date DESC', (team_name,))
        team_results = cur.fetchall()
        
        # Get all athletes associated with the team
        cur.execute('SELECT DISTINCT Athlete FROM Results WHERE Team = ?', (team_name,))
        team_athletes = cur.fetchall()
        
        # Get personal bests for each athlete in each event, now including 'Mile'
        events = ['100m', '200m', '400m', '800m', '1500m', 'Mile', '3000m', '5000m', '10000m']
        team_pbs = {}
        
        for athlete in team_athletes:
            athlete_name = athlete[0]
            team_pbs[athlete_name] = {}
            
            for event in events:
                cur.execute('''
                    SELECT Result 
                    FROM Results 
                    WHERE Team = ? 
                    AND Athlete = ? 
                    AND Event = ?
                    ORDER BY 
                        CASE 
                            WHEN Event IN ('100m', '200m', '400m', '800m', '1500m', 'Mile', '3000m', '5000m', '10000m') 
                            THEN CAST(REPLACE(Result, ':', '') AS DECIMAL) 
                        END ASC
                    LIMIT 1
                ''', (team_name, athlete_name, event))
                
                result = cur.fetchone()
                if result:
                    team_pbs[athlete_name][event] = result[0]

    return render_template('team.html', 
                         team_name=team_name, 
                         results=team_results, 
                         athletes=team_athletes,
                         team_pbs=team_pbs) 