from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from sqlite3 import Error

app = Flask(__name__)
app.config['DATABASE'] = 'track.db'

def create_connection():
    conn = None;
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
        cur.execute('SELECT * FROM Results')
        results = cur.fetchall()

        #athletes list
        cur.execute('SELECT DISTINCT Athlete FROM Results')
        athletes = cur.fetchall()

    return render_template('index.html', results=results, athletes=athletes)

@app.route('/athlete/<name>')
def athlete_profile(name):
    conn = create_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM Results WHERE Athlete = ?', (name,))
        results = cur.fetchall()

    return render_template('profile.html', results=results)

@app.route('/insert', methods=['GET', 'POST'])
def insert_result():
    if request.method == 'POST':
        conn = create_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('INSERT INTO Results (Date, Athlete, Meet, Event, Result, Team) VALUES (?, ?, ?, ?, ?, ?)',
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

if __name__ == '__main__':
    app.run(debug=True)