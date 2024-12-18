from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_wtf import CSRFProtect
from forms import ResultForm, SearchForm
from models import Result, Database

app = Flask(__name__)
app.config['DATABASE'] = 'track.db'
app.secret_key = 'your_secret_key_here'
csrf = CSRFProtect(app)

@app.route('/')
def home():
    form = SearchForm()
    results = Result.get_recent_results()
    return render_template('index.html', results=results, form=form)

@app.route('/athlete/<name>')
def athlete_profile(name):
    results, prs, athlete_info = Result.get_athlete_results(name)
    
    # preferred order of events
    preforder = ['60m', '100m', '100mH', '110mH', '200m', '300m', '400m', '400m RS', '400mH',
                '500m', '600yd', '600m', '800m', '1000m', '1500m', 'Mile',
                '3000m', '3200m', '5000m', '5K XC', '5K Road', '10000m',
                'Half Marathon', 'Marathon', 'High Jump', 'Long Jump',
                'Triple Jump', 'Shot Put', 'Discus', 'Pole Vault', 'Javelin', '4x400m']
    
    # sort prs by preferred order (handle empty prs)
    if prs:
        prs = {event: prs[event] for event in preforder if event in prs}
    
    # Get team and class with defaults
    team = athlete_info.get('Team', 'Unknown')
    athlete_class = athlete_info.get('Class', 'Unknown')
    
    return render_template('profile.html', 
                         name=name, 
                         results=results, 
                         prs=prs, 
                         team=team, 
                         athlete_class=athlete_class)

@app.route('/insert', methods=['GET', 'POST'])
def insert_result():
    form = ResultForm()
    if request.method == 'GET':
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        return render_template('insert.html', form=form, today=today)
    if request.method == 'POST':
        try:
            # Get all the arrays from the form
            dates = request.form.getlist('date[]')
            athletes = request.form.getlist('athlete[]')
            meets = request.form.getlist('meet[]')
            events = request.form.getlist('event[]')
            results = request.form.getlist('result[]')
            teams = request.form.getlist('team[]')
            
            # Insert each result
            for i in range(len(dates)):
                data = {
                    'date': dates[i],
                    'athlete': athletes[i],
                    'meet': meets[i],
                    'event': events[i],
                    'result': results[i],
                    'team': teams[i]
                }
                Result.insert_result(data)
            
            # If the request wants JSON, return JSON response
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': True})
            
            # Otherwise, flash message and redirect
            flash('Results successfully added!', 'success')
            return redirect(url_for('home'))
            
        except Exception as e:
            print(f"Error: {str(e)}")  # Debug print
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Error adding results: {str(e)}', 'error')
            
    return render_template('insert.html', form=form)

@app.route('/lookup_team/<athlete_name>')
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

@app.route('/delete', methods=['GET', 'POST'])
def delete_result():
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        if request.method == 'POST':
            cur.execute('DELETE FROM Results WHERE Result_ID = ?', (request.form.get('result_id'),))
            conn.commit()

        cur.execute('SELECT Date, Athlete, Meet_Name, Event, Result, Team FROM Results ORDER BY Result_ID DESC LIMIT 20')
        results = cur.fetchall()

    return render_template('delete.html', results=results)

@app.route('/leaderboard')
def leaderboard():
    conn = Database.get_connection()
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
                if current_event != '100m':
                    event_results.sort(key=lambda x: x[2])  # Sort event results by time
                else:
                    event_results.sort(key=lambda x: float(x[2]))  # Sort event results by time
                leaderboard_results[current_event] = event_results
            current_event = event
            event_results = []

        event_results.append(result)

    if current_event is not None:
        event_results.sort(key=lambda x: x[2])  # Sort the last event results by time
        leaderboard_results[current_event] = event_results

    #discard duplicate athletes
    for event in leaderboard_results:
        athletes = set()
        leaderboard_results[event] = [result for result in leaderboard_results[event]
                                      if not (result[1] in athletes or athletes.add(result[1]))]

    #only use top 20 results
    for event in leaderboard_results:
        leaderboard_results[event] = leaderboard_results[event][:20]

    return render_template('leaderboard.html', results=leaderboard_results)

@app.route('/team/<team_name>')
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
        
        # Get personal bests for each athlete in each event
        team_pbs = {}
        events = ['100m', '200m', '400m', '800m', '1500m', '3000m', '5000m', '10000m']
        
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
                            WHEN Event IN ('100m', '200m', '400m', '800m', '1500m', '3000m', '5000m', '10000m') 
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

@app.route('/meet/<meet_name>')
def meet_results(meet_name):
    results = Result.get_meet_results(meet_name)
    return render_template('meet.html', meet_name=meet_name, results=results)

#athlete search
@app.route('/search', methods=['GET', 'POST'])
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

@app.route('/delete_result/<int:result_id>', methods=['POST'])
def delete_athlete_result(result_id):
    try:
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM Results WHERE Result_ID = ?', (result_id,))
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting result {result_id}: {str(e)}")  # Debug logging
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5006)