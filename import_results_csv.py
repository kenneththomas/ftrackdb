import sqlite3
import csv
from datetime import datetime

# Connect to SQLite database
conn = sqlite3.connect('track.db')
c = conn.cursor()

# Read the CSV file
with open('results_csv.csv', 'r') as f:
    reader = csv.reader(f)
    next(reader)  # Skip the header row

    for row in reader:
        date, athlete, meet, event, result, team = row
        print('processing:', date, athlete, meet, event, result, team)
        for row in reader:
            # convert the date from MM/DD/YYYY to YYYY-MM-DD
            date = datetime.strptime(row[0], '%m/%d/%Y').strftime('%Y-%m-%d')
            athlete = row[1]
            meet = row[2]
            event = row[3]
            result = row[4]
            team = row[5]

        # Check for duplicates
        c.execute('''
            SELECT * FROM Results
            WHERE Date = ? AND Athlete = ? AND Meet_Name = ? AND Event = ? AND Result = ? AND Team = ?
        ''', (date, athlete, meet, event, result, team))

        if c.fetchone() is None:
            # If record does not exist in the database, insert it
            c.execute('''
                INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (date, athlete, meet, event, result, team))
        else:
            print('Record already exists:', date, athlete, meet, event, result, team)

# Commit the changes and close the connection
conn.commit()
conn.close()