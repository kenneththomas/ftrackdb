import sqlite3

# Connect to SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect('track.db')

# Create a cursor object
c = conn.cursor()

# Create table
c.execute('''
    CREATE TABLE Results (
        Result_ID INTEGER PRIMARY KEY,
        Date TEXT,
        Athlete TEXT,
        Meet_Name TEXT,
        Event TEXT,
        Result TEXT,
        Team TEXT
    )
''')

# Commit the changes and close the connection
conn.commit()
conn.close()