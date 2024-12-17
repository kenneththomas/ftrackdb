import sqlite3
from datetime import datetime

def connect_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to {db_path}: {e}")
        return None

def import_results():
    # Connect to both databases
    source_conn = connect_db('track_clean.db')
    target_conn = connect_db('track.db')
    
    if not source_conn or not target_conn:
        return
    
    try:
        # Get data from source database
        source_cur = source_conn.cursor()
        source_cur.execute('SELECT * FROM Results')
        old_results = source_cur.fetchall()
        
        # Prepare target database cursor
        target_cur = target_conn.cursor()
        
        # Get existing results to avoid duplicates
        target_cur.execute('SELECT Date, Athlete, Meet_Name, Event, Result FROM Results')
        existing_results = set(
            (str(row['Date']), row['Athlete'], row['Meet_Name'], row['Event'], str(row['Result']))
            for row in target_cur.fetchall()
        )
        
        # Counter for statistics
        imported = 0
        skipped = 0
        
        # Process each result
        for result in old_results:
            # Create a dictionary with all possible fields
            result_dict = {
                'Date': result['Date'] if 'Date' in result.keys() else None,
                'Athlete': result['Athlete'] if 'Athlete' in result.keys() else None,
                'Meet_Name': result['Meet_Name'] if 'Meet_Name' in result.keys() else None,
                'Event': result['Event'] if 'Event' in result.keys() else None,
                'Result': result['Result'] if 'Result' in result.keys() else None,
                'Team': result['Team'] if 'Team' in result.keys() else ''  # Optional field
            }
            
            # Skip if missing required fields
            if not all([result_dict['Date'], result_dict['Athlete'], 
                       result_dict['Meet_Name'], result_dict['Event'], 
                       result_dict['Result']]):
                skipped += 1
                continue
                
            # Check for duplicates
            result_tuple = (
                str(result_dict['Date']),
                result_dict['Athlete'],
                result_dict['Meet_Name'],
                result_dict['Event'],
                str(result_dict['Result'])
            )
            
            if result_tuple in existing_results:
                skipped += 1
                continue
            
            # Insert the result
            try:
                target_cur.execute('''
                    INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    result_dict['Date'],
                    result_dict['Athlete'],
                    result_dict['Meet_Name'],
                    result_dict['Event'],
                    result_dict['Result'],
                    result_dict['Team']
                ))
                imported += 1
            except sqlite3.Error as e:
                print(f"Error importing result: {result_dict}")
                print(f"Error message: {e}")
                skipped += 1
        
        # Commit changes
        target_conn.commit()
        
        print(f"Import completed:")
        print(f"- Imported: {imported} results")
        print(f"- Skipped: {skipped} results")
        
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    import_results() 