import sqlite3
from sqlite3 import Error
from flask import current_app

class Database:
    @staticmethod
    def get_connection():
        conn = None
        try:
            conn = sqlite3.connect(current_app.config['DATABASE'])
            conn.row_factory = sqlite3.Row
            # Initialize tables on connection
            Database.initialize_tables(conn)
        except Error as e:
            print(e)
        return conn

    @staticmethod
    def initialize_tables(conn):
        try:
            cur = conn.cursor()
            
            # Create Athletes table if it doesn't exist
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Athletes (
                    athlete_name TEXT PRIMARY KEY,
                    bio TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
        except Error as e:
            print(f"Error initializing tables: {e}")

class Result:
    @staticmethod
    def get_recent_results(limit=25):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date, 
                       Athlete, Meet_Name, Event, Result, Team 
                FROM Results 
                ORDER BY Date DESC 
                LIMIT ?
            ''', (limit,))
            return cur.fetchall()

    @staticmethod
    def get_athlete_results(name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Make sure to include Result_ID in the SELECT statement
            cur.execute('''
                SELECT Date, Meet_Name, Event, Result, Team, Result_ID 
                FROM Results 
                WHERE Athlete = ? 
                ORDER BY Date DESC
            ''', (name,))
            results = cur.fetchall()
            
            # Get PRs
            cur.execute("""
                SELECT Event, MIN(Result) 
                FROM Results 
                WHERE Athlete = ? 
                GROUP BY Event
                """, (name,))
            prs = dict(cur.fetchall() or [])  # Return empty dict if no PRs
            
            # Get athlete info
            cur.execute('''
                SELECT Team, Class 
                FROM Results 
                WHERE Athlete = ? 
                ORDER BY Date DESC 
                LIMIT 1
            ''', (name,))
            athlete_info = dict(zip(['Team', 'Class'], cur.fetchone() or ['Unknown', 'Unknown']))
            
            # Add bio lookup
            cur.execute('SELECT bio FROM Athletes WHERE athlete_name = ?', (name,))
            bio = cur.fetchone()
            bio = bio[0] if bio else None
            
            return results, prs, athlete_info, bio

    @staticmethod
    def get_meet_results(meet_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date,
                       Athlete, Event, Result, Team 
                FROM Results 
                WHERE Meet_Name = ? 
                ORDER BY Event, Result ASC
            ''', (meet_name,))
            return cur.fetchall()

    @staticmethod
    def insert_result(data):
        conn = Database.get_connection()
        if not conn:
            raise Exception("Could not connect to database")
        
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    'INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team) VALUES (?, ?, ?, ?, ?, ?)',
                    (data['date'], data['athlete'], data['meet'], 
                     data['event'], data['result'], data['team'])
                )
                conn.commit()
        except Exception as e:
            raise Exception(f"Failed to insert result: {str(e)}")
        finally:
            if conn:
                conn.close()

class Athlete:
    @staticmethod
    def get_bio(name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT bio FROM Athletes WHERE athlete_name = ?', (name,))
            result = cur.fetchone()
            return result[0] if result else None

    @staticmethod
    def update_bio(name, bio):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO Athletes (athlete_name, bio) 
                VALUES (?, ?)
                ON CONFLICT(athlete_name) 
                DO UPDATE SET bio = ?, updated_at = CURRENT_TIMESTAMP
            ''', (name, bio, bio))
            conn.commit()