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
            
            # Create TeamScores table if it doesn't exist
            cur.execute('''
                CREATE TABLE IF NOT EXISTS TeamScores (
                    meet_name TEXT,
                    team_name TEXT,
                    score REAL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (meet_name, team_name)
                )
            ''')
            
            # Create AthleteRankings table if it doesn't exist
            cur.execute('''
                CREATE TABLE IF NOT EXISTS AthleteRankings (
                    meet_name TEXT,
                    event TEXT,
                    date TEXT,
                    athlete TEXT,
                    ranking_before INTEGER,
                    ranking_after INTEGER,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (meet_name, event, date, athlete)
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

class TeamScore:
    @staticmethod
    def get_meet_scores(meet_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT team_name, score 
                FROM TeamScores 
                WHERE meet_name = ? 
                ORDER BY score DESC
            ''', (meet_name,))
            return cur.fetchall()

    @staticmethod
    def update_meet_scores(meet_name, team_scores):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Delete existing scores for this meet
            cur.execute('DELETE FROM TeamScores WHERE meet_name = ?', (meet_name,))
            # Insert new scores
            for team, score in team_scores.items():
                cur.execute('''
                    INSERT INTO TeamScores (meet_name, team_name, score)
                    VALUES (?, ?, ?)
                ''', (meet_name, team, score))
            conn.commit()

class AthleteRanking:
    @staticmethod
    def get_meet_rankings(meet_name):
        """Get cached rankings for a specific meet"""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT event, date, athlete, ranking_before, ranking_after
                FROM AthleteRankings 
                WHERE meet_name = ?
                ORDER BY event, date, athlete
            ''', (meet_name,))
            return cur.fetchall()

    @staticmethod
    def update_meet_rankings(meet_name, rankings_data):
        """Update cached rankings for a meet"""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Delete existing rankings for this meet
            cur.execute('DELETE FROM AthleteRankings WHERE meet_name = ?', (meet_name,))
            # Insert new rankings
            for ranking in rankings_data:
                cur.execute('''
                    INSERT INTO AthleteRankings (meet_name, event, date, athlete, ranking_before, ranking_after)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (meet_name, ranking['event'], ranking['date'], ranking['athlete'], 
                     ranking['ranking_before'], ranking['ranking_after']))
            conn.commit()

    @staticmethod
    def calculate_rankings_for_date(event, date, include_current=False):
        """Calculate rankings for an event as of a specific date"""
        from datetime import datetime, timedelta
        
        # Get date 1 year before the meet date
        meet_date = datetime.strptime(date, '%Y-%m-%d')
        one_year_ago = (meet_date - timedelta(days=365)).strftime('%Y-%m-%d')
        target_date = date if include_current else (meet_date - timedelta(days=1)).strftime('%Y-%m-%d')
        
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # For time events (lower is better)
            if 'm' in event or 'Mile' in event:
                cur.execute('''
                    WITH RankedResults AS (
                        SELECT 
                            Athlete,
                            Result,
                            ROW_NUMBER() OVER (ORDER BY Result ASC) as rank
                        FROM Results 
                        WHERE Event = ? 
                        AND Date <= ?
                        AND Date >= ?
                        GROUP BY Athlete
                        HAVING Result = MIN(Result)
                    )
                    SELECT Athlete, rank 
                    FROM RankedResults
                    ORDER BY rank
                ''', (event, target_date, one_year_ago))
            # For field events (higher is better)
            else:
                cur.execute('''
                    WITH RankedResults AS (
                        SELECT 
                            Athlete,
                            Result,
                            ROW_NUMBER() OVER (ORDER BY Result DESC) as rank
                        FROM Results 
                        WHERE Event = ? 
                        AND Date <= ?
                        AND Date >= ?
                        GROUP BY Athlete
                        HAVING Result = MAX(Result)
                    )
                    SELECT Athlete, rank 
                    FROM RankedResults
                    ORDER BY rank
                ''', (event, target_date, one_year_ago))
            
            return dict(cur.fetchall())

    @staticmethod
    def calculate_athlete_rankings(athlete_name):
        """Calculate current rankings for an athlete across all their events"""
        from datetime import datetime, timedelta
        
        # Get date 1 year ago from today
        one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            
            # Get all events the athlete has competed in
            cur.execute('''
                SELECT DISTINCT Event 
                FROM Results 
                WHERE Athlete = ?
                ORDER BY Event
            ''', (athlete_name,))
            events = [row[0] for row in cur.fetchall()]
            
            rankings = {}
            for event in events:
                # For time events (lower is better)
                if 'm' in event or 'Mile' in event:
                    cur.execute('''
                        WITH RankedResults AS (
                            SELECT 
                                Athlete,
                                Result,
                                ROW_NUMBER() OVER (ORDER BY Result ASC) as rank
                            FROM Results 
                            WHERE Event = ? 
                            AND Date >= ?
                            GROUP BY Athlete
                            HAVING Result = MIN(Result)
                        )
                        SELECT rank 
                        FROM RankedResults
                        WHERE Athlete = ?
                    ''', (event, one_year_ago, athlete_name))
                # For field events (higher is better)
                else:
                    cur.execute('''
                        WITH RankedResults AS (
                            SELECT 
                                Athlete,
                                Result,
                                ROW_NUMBER() OVER (ORDER BY Result DESC) as rank
                            FROM Results 
                            WHERE Event = ? 
                            AND Date >= ?
                            GROUP BY Athlete
                            HAVING Result = MAX(Result)
                        )
                        SELECT rank 
                        FROM RankedResults
                        WHERE Athlete = ?
                    ''', (event, one_year_ago, athlete_name))
                
                result = cur.fetchone()
                if result:
                    rankings[event] = result[0]
            
            return rankings