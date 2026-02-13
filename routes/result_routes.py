from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from models import Result, Database
from forms import ResultForm

# Create blueprint
result_bp = Blueprint('result', __name__)


@result_bp.route('/api/fill_result_blanks', methods=['POST'])
def fill_result_blanks():
    """Accept current result rows (with possible blanks), call OpenRouter LLM to fill blanks, return filled rows."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        rows = data.get('rows') or []
        if not isinstance(rows, list):
            return jsonify({'success': False, 'error': 'rows must be an array'}), 400
        from utils.openrouter import fill_result_blanks as llm_fill
        filled = llm_fill(rows)
        return jsonify({'success': True, 'rows': filled})
    except ValueError as e:
        err = str(e)
        if 'OPENROUTER_API_KEY' in err:
            return jsonify({'success': False, 'error': err}), 503
        return jsonify({'success': False, 'error': err}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@result_bp.route('/insert', methods=['GET', 'POST'])
def insert_result():
    form = ResultForm()
    if request.method == 'GET':
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        last_meet = ''
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT Meet_Name FROM Results ORDER BY Result_ID DESC LIMIT 1')
            row = cur.fetchone()
            if row:
                last_meet = row['Meet_Name'] or ''
        return render_template('insert.html', form=form, today=today, last_meet=last_meet)
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
                # Auto-fill meet name with date in YYYYMMDD format if empty
                meet_name = meets[i].strip() if meets[i] else ''
                if not meet_name and dates[i]:
                    # Convert date from YYYY-MM-DD to YYYYMMDD
                    meet_name = dates[i].replace('-', '')
                
                data = {
                    'date': dates[i],
                    'athlete': athletes[i],
                    'meet': meet_name,
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
    
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    last_meet = ''
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT Meet_Name FROM Results ORDER BY Result_ID DESC LIMIT 1')
        row = cur.fetchone()
        if row:
            last_meet = row['Meet_Name'] or ''
    return render_template('insert.html', form=form, today=today, last_meet=last_meet)

@result_bp.route('/delete', methods=['GET', 'POST'])
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

@result_bp.route('/delete_result/<int:result_id>', methods=['POST'])
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

@result_bp.route('/update_result/<int:result_id>', methods=['POST'])
def update_result(result_id):
    try:
        data = request.json
        # Map frontend field names to database column names
        field_mapping = {
            'meet': 'Meet_Name',
            'date': 'Date',
            'event': 'Event',
            'result': 'Result',
            'team': 'Team'
        }
        
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Update each field that was changed
            updates = []
            values = []
            for field, value in data.items():
                db_field = field_mapping.get(field)
                if db_field:
                    updates.append(f"{db_field} = ?")
                    values.append(value)
            values.append(result_id)
            
            query = f"UPDATE Results SET {', '.join(updates)} WHERE Result_ID = ?"
            cur.execute(query, values)
            conn.commit()
            
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error updating result {result_id}: {str(e)}")  # Debug logging
        return jsonify({'success': False, 'error': str(e)}), 500 