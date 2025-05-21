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
            
            # Create Athletes table if it doesn't exist.
            # Note: If the table already exists you may need to run an ALTER TABLE command
            # to add the new column "is_female". For a new database, include it here.
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Athletes (
                    athlete_name TEXT PRIMARY KEY,
                    bio TEXT,
                    is_female INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create Teams table if it doesn't exist
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Teams (
                    team_name TEXT PRIMARY KEY,
                    logo_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
        except Error as e:
            print(f"Error initializing tables: {e}")

class Result:
    @staticmethod
    def get_recent_results(limit=25, offset=0):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date, 
                       Athlete, Meet_Name, Event, Result, Team 
                FROM Results 
                ORDER BY Date DESC 
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            return cur.fetchall()

    @staticmethod
    def get_total_results():
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM Results')
            return cur.fetchone()[0]

    @staticmethod
    def get_athlete_results(name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Include Result_ID in the SELECT statement
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
                ORDER BY Event, 
                    CASE 
                        WHEN Event IN ('60m', '100m', '200m', '400m', '60mH', '100mH', '110mH', '400mH') 
                        THEN CAST(REPLACE(Result, ':', '') AS DECIMAL)
                        ELSE Result 
                    END ASC
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

    @staticmethod
    def get_recent_meets(limit=25, offset=0, search=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            query = '''
                SELECT DISTINCT Meet_Name, strftime('%Y-%m-%d', Date) as formatted_date
                FROM Results
            '''
            params = []
            if search:
                query += ' WHERE Meet_Name LIKE ?'
                params.append(f'%{search}%')
            query += ' ORDER BY formatted_date DESC, Meet_Name ASC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            cur.execute(query, params)
            return cur.fetchall()

    @staticmethod
    def get_total_meets(search=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            query = 'SELECT COUNT(*) FROM (SELECT DISTINCT Meet_Name, strftime("%Y-%m-%d", Date) as formatted_date FROM Results'
            params = []
            if search:
                query += ' WHERE Meet_Name LIKE ?'
                params.append(f'%{search}%')
            query += ')'
            cur.execute(query, params)
            return cur.fetchone()[0]

    @staticmethod
    def get_recent_winners(limit=25, offset=0):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                WITH RankedResults AS (
                    SELECT 
                        strftime('%Y-%m-%d', Date) as formatted_date,
                        Athlete,
                        Meet_Name,
                        Event,
                        Result,
                        Team,
                        ROW_NUMBER() OVER (
                            PARTITION BY Meet_Name, Event 
                            ORDER BY 
                                CASE 
                                    WHEN Event IN ('60m', '100m', '200m', '400m', '800m', '1500m', 'Mile', '3000m', '5000m', '10000m', '60mH', '100mH', '110mH', '400mH') 
                                    THEN CAST(REPLACE(Result, ':', '') AS DECIMAL)
                                    ELSE Result 
                                END ASC
                        ) as rn
                    FROM Results
                )
                SELECT formatted_date, Athlete, Meet_Name, Event, Result, Team
                FROM RankedResults
                WHERE rn = 1
                ORDER BY formatted_date DESC, Meet_Name, Event
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            return cur.fetchall()

    @staticmethod
    def get_total_winners():
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT Meet_Name, Event
                    FROM Results
                )
            ''')
            return cur.fetchone()[0]

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

    @staticmethod
    def update_gender(name, is_female):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO Athletes (athlete_name, is_female)
                VALUES (?, ?)
                ON CONFLICT(athlete_name)
                DO UPDATE SET is_female = ?, updated_at = CURRENT_TIMESTAMP
            ''', (name, is_female, is_female))
            conn.commit()

    @staticmethod
    def get_gender(name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT is_female FROM Athletes WHERE athlete_name = ?', (name,))
            result = cur.fetchone()
            return bool(result[0]) if result and result[0] is not None else False

class Team:
    @staticmethod
    def get_team_info(team_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT logo_url FROM Teams WHERE team_name = ?', (team_name,))
            result = cur.fetchone()
            return {'logo_url': result[0] if result else None}

    @staticmethod
    def update_team_logo(team_name, logo_url):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO Teams (team_name, logo_url) 
                VALUES (?, ?)
                ON CONFLICT(team_name) 
                DO UPDATE SET logo_url = ?, updated_at = CURRENT_TIMESTAMP
            ''', (team_name, logo_url, logo_url))
            conn.commit()