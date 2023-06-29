import sqlite3

def normalization():
    # Connect to SQLite database (or create it if it doesn't exist)
    conn = sqlite3.connect('track.db')

    # Create a cursor object
    c = conn.cursor()

    #In table Results, find results that start with a 0, and get rid of the 0
    c.execute('SELECT * FROM Results WHERE Result LIKE "0%"')
    results = c.fetchall()
    for result in results:
        result_id = result[0]
        result_time = result[5]
        result_time = result_time[1:]
        c.execute('UPDATE Results SET Result = ? WHERE Result_ID = ?', (result_time, result_id))

    # Commit the changes and close the connection
    conn.commit()
    conn.close()
