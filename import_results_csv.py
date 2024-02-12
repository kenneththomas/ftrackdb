import sqlite3
import csv
from datetime import datetime
import db_normalization

# Connect to SQLite database
conn = sqlite3.connect('track.db')
c = conn.cursor()

# Read the CSV file
with open('results_csv.csv', 'r') as f:
    reader = csv.reader(f)
    next(reader)  # Skip the header row

    for row in reader:
        # Convert date to YYYY-MM-DD format
        if len(row[0]) == 10:
            date = datetime.strptime(row[0], '%m/%d/%Y').strftime('%Y-%m-%d')
        elif len(row[0]) == 8:
            print(row[0])
            date = datetime.strptime(row[0], '%m/%d/%Y').strftime('%Y-%m-%d')
        #elif 2/25/2022
        elif len(row[0]) == 9:
            print(row[0])
            date = datetime.strptime(row[0], '%m/%d/%Y').strftime('%Y-%m-%d')
        # else set date to today
        else:
            date = datetime.today().strftime('%Y-%m-%d')

        #if the length of the team name is 0, replace it with the team name of the athlete
        if len(row[5]) == 0:
            c.execute('SELECT Team FROM Results WHERE Athlete = ?', (row[1],))
            team = c.fetchone()
            print(f'No team name for {row[1]} found. Using {team} instead.')
            if team is None:
                team = 'Unknown'
            else:
                row[5] = team[0]

        #if result starts with a 0, strip it
        if row[4][0] == '0':
            row[4] = row[4][1:]
        
        athlete = row[1]
        meet = row[2]
        event = row[3]
        result = row[4]
        team = row[5].replace('/', ' ') # slashes in team name breaks webpage creation


        print('processing:', date, athlete, meet, event, result, team)

        # check for duplicates, do not consider the date or result

        c.execute('''
            SELECT * FROM Results
            WHERE Athlete = ? AND Meet_Name = ? AND Event = ? AND Team = ?
        ''', (athlete, meet, event, team))

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

# Normalize the database
db_normalization.normalization()