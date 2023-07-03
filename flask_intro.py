from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from sqlite3 import Error

app = Flask(__name__)
app.config['DATABASE'] = 'track.db'

def create_connection():
    conn = None
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
    except Error as e:
        print(e)
    return conn

@app.route('/')
def home():
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM Results ORDER BY Date DESC LIMIT 25')
        results = cur.fetchall()

        # athletes list
        cur.execute('SELECT DISTINCT Athlete FROM Results')
        athletes = cur.fetchall()

    return render_template('index.html', results=results, athletes=athletes)

@app.route('/athlete/<name>')
def athlete_profile(name):
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        # Select all results for the athlete
        cur.execute('SELECT * FROM Results WHERE Athlete = ? ORDER BY Date DESC', (name,))
        results = cur.fetchall()
        
        # Select PRs for each event
        cur.execute("""
            SELECT Event, MIN(Result) 
            FROM Results 
            WHERE Athlete = ? 
            GROUP BY Event
            """, (name,))
        prs = cur.fetchall()
        prs = {event: result for event, result in prs}  # Convert to dict for easier usage in the template

    return render_template('profile.html', name=name, results=results, prs=prs)

@app.route('/insert', methods=['GET', 'POST'])
def insert_result():
    if request.method == 'POST':
        conn = create_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team) VALUES (?, ?, ?, ?, ?, ?)',
                        (request.form.get('date'), request.form.get('athlete'), request.form.get('meet'),
                        request.form.get('event'), request.form.get('result'), request.form.get('team')))
            conn.commit()

        return redirect(url_for('home'))

    return render_template('insert.html')

@app.route('/delete', methods=['GET', 'POST'])
def delete_result():
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        if request.method == 'POST':
            cur.execute('DELETE FROM Results WHERE Result_ID = ?', (request.form.get('result_id'),))
            conn.commit()

        cur.execute('SELECT * FROM Results ORDER BY Result_ID DESC LIMIT 20')
        results = cur.fetchall()

    return render_template('delete.html', results=results)

@app.route('/leaderboard')
def leaderboard():
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT Event, Athlete, Result, Team FROM Results ORDER BY Event ASC, Result ASC')
        results = cur.fetchall()

    leaderboard_results = {}
    current_event = None
    event_results = []

    for result in results:
        event = result[0]
        if current_event is None or event != current_event:
            if current_event is not None:
                event_results.sort(key=lambda x: x[2])  # Sort event results by time
                leaderboard_results[current_event] = event_results
            current_event = event
            event_results = []

        event_results.append(result)

    if current_event is not None:
        event_results.sort(key=lambda x: x[2])  # Sort the last event results by time
        leaderboard_results[current_event] = event_results

    #discard duplicate athletes
    for event in leaderboard_results:
        athletes = []
        for result in leaderboard_results[event]:
            if result[1] in athletes:
                leaderboard_results[event].remove(result)
            else:
                athletes.append(result[1])

    #only use top 20 results
    for event in leaderboard_results:
        leaderboard_results[event] = leaderboard_results[event][:20]

    return render_template('leaderboard.html', results=leaderboard_results)

@app.route('/team/<team_name>')
def team_results(team_name):
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT Date, Athlete, Meet_Name, Event, Result FROM Results WHERE Team = ? ORDER BY Date DESC', (team_name,))
        team_results = cur.fetchall()
        # get all athletes associated with the team
        cur.execute('SELECT DISTINCT Athlete FROM Results WHERE Team = ?', (team_name,))
        team_athletes = cur.fetchall()

    return render_template('team.html', team_name=team_name, results=team_results, athletes=team_athletes)

@app.route('/meet/<meet_name>')
def meet_results(meet_name):
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT Date, Athlete, Event, Result, Team FROM Results WHERE Meet_Name = ? ORDER BY Event, Result ASC', (meet_name,))
        meet_results = cur.fetchall()

    return render_template('meet.html', meet_name=meet_name, results=meet_results)


if __name__ == '__main__':
    app.run(debug=True)