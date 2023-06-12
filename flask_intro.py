import sqlite3
from flask import Flask, render_template
app = Flask(__name__)

@app.route('/')
def home():
    # Connect to your database and fetch results
    conn = sqlite3.connect('track.db')
    c = conn.cursor()
    c.execute('SELECT * FROM Results')
    results = c.fetchall()

    #athletes list
    c.execute('SELECT DISTINCT Athlete FROM Results')
    athletes = c.fetchall()

    conn.close()

    # Pass results to your template
    return render_template('index.html', results=results, athletes=athletes)

@app.route('/athlete/<name>')
def athlete_profile(name):
    conn = sqlite3.connect('track.db')
    c = conn.cursor()

    # Retrieve all results for this athlete
    c.execute('SELECT * FROM Results WHERE Athlete = ?', (name,))
    results = c.fetchall()

    conn.close()

    return render_template('profile.html', results=results)


if __name__ == '__main__':
    app.run(debug=True)