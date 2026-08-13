import sqlite3
from sqlite3 import Error
from flask import current_app

from utils.rankings import (
    RANKING_ALGORITHM_VERSION,
    canonical_event,
    placements_from_rows,
    rank_performances,
    ranking_window_start,
)

class Database:
    @staticmethod
    def get_connection():
        # timeout helps prevent "database is locked" on rapid successive writes
        conn = sqlite3.connect(current_app.config['DATABASE'], timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            Database.initialize_tables(conn)
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def initialize_tables(conn):
        try:
            cur = conn.cursor()
            
            # Create Results table if it doesn't exist (original schema from create_db.py)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Results (
                    Result_ID INTEGER PRIMARY KEY,
                    Date TEXT,
                    Athlete TEXT,
                    Meet_Name TEXT,
                    Event TEXT,
                    Result TEXT,
                    Team TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Meets (
                    meet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meet_name TEXT NOT NULL UNIQUE,
                    start_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('''
                INSERT OR IGNORE INTO Meets (meet_name, start_date)
                SELECT Meet_Name, MIN(Date) FROM Results
                WHERE Meet_Name IS NOT NULL AND TRIM(Meet_Name) != ''
                GROUP BY Meet_Name
                ORDER BY MIN(Date), Meet_Name COLLATE NOCASE
            ''')
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
            cur.execute("PRAGMA table_info(AthleteRankings)")
            ranking_columns = {row[1] for row in cur.fetchall()}
            for column, definition in (
                ('mark_before', 'TEXT'),
                ('mark_after', 'TEXT'),
                ('algorithm_version', 'INTEGER NOT NULL DEFAULT 2'),
            ):
                if column not in ranking_columns:
                    cur.execute(f"ALTER TABLE AthleteRankings ADD COLUMN {column} {definition}")
            
            # Create Comments table if it doesn't exist
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Comments (
                    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_type TEXT NOT NULL,
                    page_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parent_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_id) REFERENCES Comments(comment_id) ON DELETE CASCADE
                )
            ''')
            
            # Create BoardPosts table (Reddit-style message board)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS BoardPosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_display_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parent_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_ai_generated INTEGER DEFAULT 0,
                    ai_prompt TEXT,
                    page_type TEXT DEFAULT 'global',
                    page_id TEXT DEFAULT '',
                    FOREIGN KEY (parent_id) REFERENCES BoardPosts(id) ON DELETE CASCADE
                )
            ''')
            # Add columns to existing BoardPosts table if they were created before page_type/page_id existed
            cur.execute("PRAGMA table_info(BoardPosts)")
            columns = [row[1] for row in cur.fetchall()]
            if 'page_type' not in columns:
                cur.execute("ALTER TABLE BoardPosts ADD COLUMN page_type TEXT DEFAULT 'global'")
            if 'page_id' not in columns:
                cur.execute("ALTER TABLE BoardPosts ADD COLUMN page_id TEXT DEFAULT ''")
            
            # Stagger (ELO-style placement ranking): one score per athlete per event
            cur.execute('''
                CREATE TABLE IF NOT EXISTS StaggerScores (
                    athlete TEXT,
                    event TEXT,
                    score REAL NOT NULL DEFAULT 1000,
                    PRIMARY KEY (athlete, event)
                )
            ''')
            # Deltas applied per meet so we can revert and re-rank
            cur.execute('''
                CREATE TABLE IF NOT EXISTS StaggerHistory (
                    meet_name TEXT,
                    event TEXT,
                    date TEXT,
                    athlete TEXT,
                    delta REAL NOT NULL,
                    PRIMARY KEY (meet_name, event, date, athlete)
                )
            ''')
            cur.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'StaggerRatedMeets'")
            stagger_rated_meets_existed = cur.fetchone() is not None
            cur.execute('''
                CREATE TABLE IF NOT EXISTS StaggerRatedMeets (
                    meet_name TEXT PRIMARY KEY,
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    algorithm_version INTEGER NOT NULL DEFAULT 2
                )
            ''')
            # Preserve which meets were rated before deterministic replay existed.
            if not stagger_rated_meets_existed:
                cur.execute('''
                    INSERT OR IGNORE INTO StaggerRatedMeets (meet_name)
                    SELECT DISTINCT meet_name FROM StaggerHistory
                ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS RankingState (
                    state_key TEXT PRIMARY KEY,
                    state_value INTEGER NOT NULL DEFAULT 0
                )
            ''')
            cur.execute(
                "INSERT OR IGNORE INTO RankingState (state_key, state_value) VALUES ('stagger_dirty', ?)",
                (0 if stagger_rated_meets_existed else 1,),
            )

            # Create RelayTeams table for explicit relay entries
            cur.execute('''
                CREATE TABLE IF NOT EXISTS RelayTeams (
                    Relay_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Date TEXT,
                    Meet_Name TEXT,
                    Team TEXT,
                    Event TEXT,
                    Total_Result TEXT,
                    Team_Designation TEXT DEFAULT 'A'
                )
            ''')

            # RelayLegs table for individual legs of explicit relays
            cur.execute('''
                CREATE TABLE IF NOT EXISTS RelayLegs (
                    Leg_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Relay_ID INTEGER,
                    Leg_Number INTEGER,
                    Athlete TEXT,
                    Split_Event TEXT,
                    Split_Result TEXT,
                    FOREIGN KEY (Relay_ID) REFERENCES RelayTeams(Relay_ID) ON DELETE CASCADE
                )
            ''')

            conn.commit()
        except Error as e:
            raise RuntimeError("Error initializing database tables") from e

class Result:
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
            # Convert sqlite3.Row objects to tuples if needed
            results = [tuple(r) for r in results] if results else []
            
            # Get PRs with dates - simple approach with numeric parsing in Python
            cur.execute("""
                SELECT Event, Result, Date, Meet_Name
                FROM Results
                WHERE Athlete = ?
                ORDER BY Event, Date
            """, (name,))
            rows = cur.fetchall()
            
            # Find best result for each event using proper numeric comparison
            prs = {}
            event_rows = {}
            for row in rows:
                event = row[0]
                if event not in event_rows:
                    event_rows[event] = []
                event_rows[event].append((row[1], row[2], row[3]))  # (result, date, meet)
            
            for event, event_results in event_rows.items():
                if not event_results:
                    continue
                best_result = None
                best_numeric = None
                best_date = None
                best_meet = None
                for result_str, date, meet in event_results:
                    if not result_str:
                        continue
                    try:
                        # Parse the result to a numeric value
                        if ':' in result_str:
                            # Time format like 1:52.34
                            parts = result_str.split(':')
                            numeric = float(parts[0]) * 60 + float(parts[1])
                        else:
                            numeric = float(result_str)
                        
                        if best_numeric is None:
                            best_result = result_str
                            best_numeric = numeric
                            best_date = date
                            best_meet = meet
                        elif 'm' in event or 'H' in event or 'XC' in event or 'Road' in event or 'Marathon' in event:
                            # For running events, lower is better
                            if numeric < best_numeric:
                                best_result = result_str
                                best_numeric = numeric
                                best_date = date
                                best_meet = meet
                        else:
                            # For field events, higher is better
                            if numeric > best_numeric:
                                best_result = result_str
                                best_numeric = numeric
                                best_date = date
                                best_meet = meet
                    except (ValueError, IndexError):
                        # If parsing fails, use the first result as fallback
                        if best_result is None:
                            best_result = result_str
                            best_date = date
                            best_meet = meet
                
                if best_result is not None:
                    prs[event] = {'result': best_result, 'date': best_date, 'meet': best_meet}
            
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
    def get_meet_results_with_ids(meet_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date,
                       Athlete, Event, Result, Team, Result_ID
                FROM Results
                WHERE Meet_Name = ?
                ORDER BY Event,
                    CASE
                        WHEN Event IN ('60m', '100m', '200m', '400m', '60mH', '100mH', '110mH',
                        '400mH')
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
                cur.execute('''
                    INSERT INTO Meets (meet_name, start_date) VALUES (?, ?)
                    ON CONFLICT(meet_name) DO UPDATE SET start_date =
                        CASE
                            WHEN Meets.start_date IS NULL OR excluded.start_date < Meets.start_date
                            THEN excluded.start_date ELSE Meets.start_date
                        END
                ''', (data['meet'], data['date']))
                conn.commit()
            StaggerScore.invalidate()
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
    def get_meets_for_month(year, month, search=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            query = '''
                SELECT DISTINCT Meet_Name, strftime('%Y-%m-%d', Date) as formatted_date
                FROM Results
                WHERE strftime('%Y', Date) = ? AND strftime('%m', Date) = ?
            '''
            params = [str(year), f'{month:02d}']
            if search:
                query += ' AND Meet_Name LIKE ?'
                params.append(f'%{search}%')
            query += ' ORDER BY formatted_date ASC, Meet_Name ASC'
            cur.execute(query, params)
            return cur.fetchall()

    @staticmethod
    def get_meets_for_date(date, search=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            query = '''
                SELECT DISTINCT Meet_Name, strftime('%Y-%m-%d', Date) as formatted_date
                FROM Results
                WHERE strftime('%Y-%m-%d', Date) = ?
            '''
            params = [date]
            if search:
                query += ' AND Meet_Name LIKE ?'
                params.append(f'%{search}%')
            query += ' ORDER BY Meet_Name ASC'
            cur.execute(query, params)
            return cur.fetchall()

    @staticmethod
    def get_latest_meet_date(search=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            query = '''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date
                FROM Results
            '''
            params = []
            if search:
                query += ' WHERE Meet_Name LIKE ?'
                params.append(f'%{search}%')
            query += ' ORDER BY formatted_date DESC LIMIT 1'
            cur.execute(query, params)
            row = cur.fetchone()
            return row[0] if row else None

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
    def _winner_filter_clause(search=None, event=None, team=None):
        clauses = ['rn = 1']
        params = []

        if search:
            clauses.append('(Athlete LIKE ? OR Meet_Name LIKE ?)')
            search_pattern = f'%{search}%'
            params.extend([search_pattern, search_pattern])
        if event:
            clauses.append('Event = ?')
            params.append(event)
        if team:
            clauses.append('Team = ?')
            params.append(team)

        return ' AND '.join(clauses), params

    @staticmethod
    def get_recent_winners(limit=25, offset=0, search=None, event=None, team=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            where_clause, params = Result._winner_filter_clause(search, event, team)
            cur.execute(f'''
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
                WHERE {where_clause}
                ORDER BY formatted_date DESC, Meet_Name, Event
                LIMIT ? OFFSET ?
            ''', (*params, limit, offset))
            return cur.fetchall()

    @staticmethod
    def get_total_winners(search=None, event=None, team=None):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            where_clause, params = Result._winner_filter_clause(search, event, team)
            cur.execute(f'''
                WITH RankedResults AS (
                    SELECT
                        Athlete,
                        Meet_Name,
                        Event,
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
                SELECT COUNT(*)
                FROM RankedResults
                WHERE {where_clause}
            ''', params)
            return cur.fetchone()[0]

    @staticmethod
    def get_winner_filter_options():
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                WITH RankedResults AS (
                    SELECT
                        Event,
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
                SELECT Event, Team
                FROM RankedResults
                WHERE rn = 1
            ''')
            rows = cur.fetchall()

        events = sorted({row[0] for row in rows if row[0]}, key=str.casefold)
        teams = sorted({row[1] for row in rows if row[1]}, key=str.casefold)
        return events, teams

class Athlete:
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
        """Return the latest automatically generated snapshots for a meet."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT event, date, athlete, ranking_before, ranking_after
                FROM AthleteRankings 
                WHERE meet_name = ?
                ORDER BY event, date, athlete
            ''', (meet_name,))
            rows = cur.fetchall()
        conn.close()
        return rows

    @staticmethod
    def update_meet_rankings(meet_name, rankings_data):
        """Atomically replace a meet's derived ranking snapshots."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM AthleteRankings WHERE meet_name = ?', (meet_name,))
            for ranking in rankings_data:
                cur.execute('''
                    INSERT INTO AthleteRankings
                        (meet_name, event, date, athlete, ranking_before, ranking_after,
                         mark_before, mark_after, algorithm_version, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    meet_name, ranking['event'], ranking['date'], ranking['athlete'],
                    ranking.get('ranking_before'), ranking.get('ranking_after'),
                    ranking.get('mark_before'), ranking.get('mark_after'),
                    RANKING_ALGORITHM_VERSION,
                ))
            conn.commit()
        conn.close()

    @staticmethod
    def _rank_event_at_meet(cur, event, date, meet_name, include_meet):
        """Rank an event at a deterministic (date, meet name) boundary."""
        event = canonical_event(event)
        start_date = ranking_window_start(date)
        cur.execute('SELECT meet_id FROM Meets WHERE meet_name = ?', (meet_name,))
        meet_row = cur.fetchone()
        if not meet_row:
            raise ValueError(f'Unknown meet: {meet_name}')
        meet_id = meet_row[0]
        comparison = '<=' if include_meet else '<'
        cur.execute(f'''
            SELECT results.Athlete AS athlete, results.Result AS result
            FROM Results AS results
            JOIN Meets AS meets ON meets.meet_name = results.Meet_Name
            WHERE TRIM(results.Event) = ? COLLATE NOCASE
              AND results.Date >= ? AND results.Date <= ?
              AND (results.Date < ? OR (results.Date = ? AND meets.meet_id {comparison} ?))
        ''', (event, start_date, date, date, date, meet_id))
        return rank_performances(cur.fetchall(), event)

    @staticmethod
    def refresh_meet_rankings(meet_name):
        """Rebuild all performance-ranking snapshots for a meet.

        Same-day meets are ordered by name until the database gains stable meet
        IDs. Multiple attempts/rounds by an athlete collapse to their best mark.
        """
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT DISTINCT TRIM(Event), Date
                FROM Results
                WHERE Meet_Name = ? AND Event NOT LIKE '% RS' AND Event NOT LIKE '% Relay'
                ORDER BY Date, TRIM(Event)
            ''', (meet_name,))
            event_dates = cur.fetchall()
            snapshots = []
            for event, date in event_dates:
                before = AthleteRanking._rank_event_at_meet(cur, event, date, meet_name, False)
                after = AthleteRanking._rank_event_at_meet(cur, event, date, meet_name, True)
                cur.execute('''
                    SELECT DISTINCT Athlete FROM Results
                    WHERE Meet_Name = ? AND Date = ? AND TRIM(Event) = ? COLLATE NOCASE
                ''', (meet_name, date, event))
                for row in cur.fetchall():
                    athlete = row[0]
                    before_data = before.get(athlete, {})
                    after_data = after.get(athlete, {})
                    snapshots.append({
                        'event': event, 'date': date, 'athlete': athlete,
                        'ranking_before': before_data.get('rank'),
                        'ranking_after': after_data.get('rank'),
                        'mark_before': before_data.get('mark'),
                        'mark_after': after_data.get('mark'),
                    })
        conn.close()
        AthleteRanking.update_meet_rankings(meet_name, snapshots)
        return snapshots

    @staticmethod
    def calculate_athlete_rankings(athlete_name):
        """Calculate current 365-day rankings through the shared numeric engine."""
        from datetime import datetime, timedelta
        today = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT DISTINCT TRIM(Event) FROM Results
                WHERE Athlete = ?
                  AND Event NOT LIKE '% RS' AND Event NOT LIKE '% Relay'
                ORDER BY Event
            ''', (athlete_name,))
            events = [row[0] for row in cur.fetchall()]
            rankings = {}
            for event in events:
                cur.execute('''
                    SELECT Athlete AS athlete, Result AS result FROM Results
                    WHERE TRIM(Event) = ? COLLATE NOCASE AND Date >= ? AND Date <= ?
                ''', (event, start_date, today))
                athlete_data = rank_performances(cur.fetchall(), event).get(athlete_name)
                if athlete_data:
                    rankings[event] = athlete_data['rank']
        conn.close()
        return rankings

class Comment:
    @staticmethod
    def get_comments(page_type, page_id):
        """Get all comments for a specific page, organized in a threaded structure"""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT comment_id, username, content, parent_id, created_at
                FROM Comments 
                WHERE page_type = ? AND page_id = ?
                ORDER BY created_at ASC
            ''', (page_type, page_id))
            comments = cur.fetchall()
            
            # Organize comments into a threaded structure
            comment_dict = {}
            root_comments = []
            
            for comment in comments:
                comment_dict[comment[0]] = {
                    'comment_id': comment[0],
                    'username': comment[1],
                    'content': comment[2],
                    'parent_id': comment[3],
                    'created_at': comment[4],
                    'replies': []
                }
            
            for comment_id, comment in comment_dict.items():
                if comment['parent_id'] is None:
                    root_comments.append(comment)
                else:
                    parent = comment_dict.get(comment['parent_id'])
                    if parent:
                        parent['replies'].append(comment)
            
            return root_comments

    @staticmethod
    def add_comment(page_type, page_id, username, content, parent_id=None):
        """Add a new comment"""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO Comments (page_type, page_id, username, content, parent_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (page_type, page_id, username, content, parent_id))
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def delete_comment(comment_id):
        """Delete a comment and all its replies"""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM Comments WHERE comment_id = ?', (comment_id,))
            conn.commit()

    @staticmethod
    def get_comment_count(page_type, page_id):
        """Get the total number of comments for a page"""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT COUNT(*) FROM Comments 
                WHERE page_type = ? AND page_id = ?
            ''', (page_type, page_id))
            return cur.fetchone()[0]


class BoardPost:
    @staticmethod
    def get_threaded_posts(page_type='global', page_id=''):
        """Get board posts for the given scope, organized in a threaded structure (roots have parent_id NULL)."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT id, author_display_name, content, parent_id, created_at, is_ai_generated, ai_prompt
                FROM BoardPosts
                WHERE page_type = ? AND page_id = ?
                ORDER BY created_at ASC
            ''', (page_type, page_id or ''))
            rows = cur.fetchall()
            post_dict = {}
            root_posts = []
            for row in rows:
                post_dict[row[0]] = {
                    'id': row[0],
                    'author_display_name': row[1],
                    'content': row[2],
                    'parent_id': row[3],
                    'created_at': row[4],
                    'is_ai_generated': bool(row[5]) if row[5] is not None else False,
                    'ai_prompt': row[6],
                    'replies': []
                }
            for post_id, post in post_dict.items():
                if post['parent_id'] is None:
                    root_posts.append(post)
                else:
                    parent = post_dict.get(post['parent_id'])
                    if parent:
                        parent['replies'].append(post)
            return root_posts

    @staticmethod
    def add_post(author_display_name, content, parent_id=None, is_ai_generated=False, ai_prompt=None, page_type='global', page_id=''):
        """Add a new board post. Returns the new post id."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO BoardPosts (author_display_name, content, parent_id, is_ai_generated, ai_prompt, page_type, page_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (author_display_name, content, parent_id, 1 if is_ai_generated else 0, ai_prompt, page_type, page_id or ''))
            conn.commit()
            return cur.lastrowid


# --- Stagger (normalized multiplayer Elo placement ranking) ---
# A single event appearance can move a score by at most this many points,
# regardless of the number of athletes in the field.
STAGGER_K = 128
STAGGER_FLOOR = 200
STAGGER_CEILING = 2000
STAGGER_INITIAL = 1000


def _stagger_expected(rating_winner, rating_loser):
    """Expected score for the winner (0-1). Winner has rating_winner, loser has rating_loser."""
    return 1.0 / (1.0 + 10.0 ** ((rating_loser - rating_winner) / 400.0))


def _stagger_dampen(rating, delta):
    """Clamp new rating to [STAGGER_FLOOR, STAGGER_CEILING]."""
    new_r = rating + delta
    return max(STAGGER_FLOOR, min(STAGGER_CEILING, new_r))


def _stagger_deltas_for_placements(placements_by_key, ratings):
    """Compute one meet from an in-memory rating state, then advance it."""
    deltas = []
    for (event, date), records in sorted(placements_by_key.items()):
        n = len(records)
        if not n:
            continue
        matchup_deltas = {record['athlete']: 0.0 for record in records}
        for i in range(n):
            for j in range(i + 1, n):
                left, right = records[i], records[j]
                left_key = (left['athlete'], event)
                right_key = (right['athlete'], event)
                left_rating = ratings.get(left_key, STAGGER_INITIAL)
                right_rating = ratings.get(right_key, STAGGER_INITIAL)
                expected_left = _stagger_expected(left_rating, right_rating)
                if left['place'] < right['place']:
                    actual_left = 1.0
                elif left['place'] > right['place']:
                    actual_left = 0.0
                else:
                    actual_left = 0.5
                matchup_deltas[left['athlete']] += actual_left - expected_left
                matchup_deltas[right['athlete']] += (1.0 - actual_left) - (1.0 - expected_left)

        opponent_count = n - 1
        for athlete, matchup_delta in matchup_deltas.items():
            delta = STAGGER_K * matchup_delta / opponent_count if opponent_count else 0.0
            key = (athlete, event)
            ratings[key] = _stagger_dampen(ratings.get(key, STAGGER_INITIAL), delta)
            deltas.append((event, date, athlete, delta))
    return deltas


class StaggerScore:
    @staticmethod
    def invalidate():
        """Mark Stagger derived data dirty after any result mutation."""
        conn = Database.get_connection()
        with conn:
            conn.execute("UPDATE RankingState SET state_value = 1 WHERE state_key = 'stagger_dirty'")
        conn.close()

    @staticmethod
    def ensure_current():
        conn = Database.get_connection()
        with conn:
            row = conn.execute(
                "SELECT state_value FROM RankingState WHERE state_key = 'stagger_dirty'"
            ).fetchone()
        conn.close()
        if row and row[0]:
            StaggerScore.rebuild_all()

    @staticmethod
    def rate_meet(meet_name):
        """Activate a meet and atomically replay every rated meet chronologically."""
        conn = Database.get_connection()
        with conn:
            conn.execute('''
                INSERT INTO StaggerRatedMeets (meet_name, algorithm_version)
                VALUES (?, ?)
                ON CONFLICT(meet_name) DO UPDATE SET algorithm_version = excluded.algorithm_version
            ''', (meet_name, RANKING_ALGORITHM_VERSION))
            conn.execute("UPDATE RankingState SET state_value = 1 WHERE state_key = 'stagger_dirty'")
        conn.close()
        StaggerScore.rebuild_all()

    @staticmethod
    def rebuild_all():
        """Rebuild scores/history from source results in stable chronological order."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Lock before reading source results so a concurrent edit cannot
            # produce a history assembled from two different database states.
            cur.execute('BEGIN IMMEDIATE')
            cur.execute('''
                SELECT rated.meet_name, MIN(results.Date) AS meet_date, meets.meet_id
                FROM StaggerRatedMeets AS rated
                LEFT JOIN Results AS results ON results.Meet_Name = rated.meet_name
                LEFT JOIN Meets AS meets ON meets.meet_name = rated.meet_name
                GROUP BY rated.meet_name
                ORDER BY COALESCE(meet_date, '9999-12-31'), meets.meet_id, rated.meet_name COLLATE NOCASE
            ''')
            rated_meets = [row[0] for row in cur.fetchall()]
            ratings = {}
            history = []
            for meet_name in rated_meets:
                cur.execute('''
                    SELECT Date, Athlete, Event, Result
                    FROM Results WHERE Meet_Name = ?
                    ORDER BY Date, Event, Result_ID
                ''', (meet_name,))
                placements = placements_from_rows(cur.fetchall())
                for event, date, athlete, delta in _stagger_deltas_for_placements(placements, ratings):
                    history.append((meet_name, event, date, athlete, delta))

            cur.execute('DELETE FROM StaggerScores')
            cur.execute('DELETE FROM StaggerHistory')
            cur.executemany(
                'INSERT INTO StaggerScores (athlete, event, score) VALUES (?, ?, ?)',
                [(athlete, event, score) for (athlete, event), score in ratings.items()],
            )
            cur.executemany('''
                INSERT INTO StaggerHistory (meet_name, event, date, athlete, delta)
                VALUES (?, ?, ?, ?, ?)
            ''', history)
            cur.execute("UPDATE RankingState SET state_value = 0 WHERE state_key = 'stagger_dirty'")
        conn.close()

    @staticmethod
    def get_score_if_exists(athlete, event):
        """Return current stagger score for (athlete, event), or None if no score exists yet."""
        StaggerScore.ensure_current()
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT score FROM StaggerScores WHERE athlete = ? AND event = ?',
                (athlete, event)
            )
            row = cur.fetchone()
        conn.close()
        return float(row[0]) if row else None

    @staticmethod
    def get_scores_for_athlete(athlete):
        """Return dict event -> score for an athlete."""
        StaggerScore.ensure_current()
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT event, score FROM StaggerScores WHERE athlete = ?',
                (athlete,)
            )
            scores = {row[0]: float(row[1]) for row in cur.fetchall()}
        conn.close()
        return scores

    @staticmethod
    def get_peak_scores_for_athlete(athlete):
        """Return dict event -> highest known stagger score for an athlete."""
        StaggerScore.ensure_current()
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT event, date, meet_name, delta
                FROM StaggerHistory
                WHERE athlete = ?
                ORDER BY event, date, meet_name
            ''', (athlete,))
            history_rows = cur.fetchall()
        conn.close()

        peak_scores = {}
        running_scores = {}
        for event, _date, _meet_name, delta in history_rows:
            current = running_scores.get(event, STAGGER_INITIAL)
            new_score = _stagger_dampen(current, float(delta))
            running_scores[event] = new_score
            peak_scores[event] = max(peak_scores.get(event, STAGGER_INITIAL), new_score)

        return peak_scores

    @staticmethod
    def get_meet_history(meet_name):
        """Return list of (event, date, athlete, delta) for a meet."""
        StaggerScore.ensure_current()
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT event, date, athlete, delta
                FROM StaggerHistory
                WHERE meet_name = ?
                ORDER BY event, date, athlete
            ''', (meet_name,))
            rows = cur.fetchall()
        conn.close()
        return rows

    @staticmethod
    def revert_meet(meet_name):
        """Deactivate a meet and replay the remaining rated meets."""
        conn = Database.get_connection()
        with conn:
            conn.execute('DELETE FROM StaggerRatedMeets WHERE meet_name = ?', (meet_name,))
            conn.execute("UPDATE RankingState SET state_value = 1 WHERE state_key = 'stagger_dirty'")
        conn.close()
        StaggerScore.rebuild_all()

    @staticmethod
    def apply_meet_deltas(meet_name, deltas):
        """Compatibility shim: activate and deterministically rebuild the meet."""
        StaggerScore.rate_meet(meet_name)


class RelayTeam:
    RELAY_CONFIG = {
        '4x100m': ['100m', '100m', '100m', '100m'],
        '4x200m': ['200m', '200m', '200m', '200m'],
        '4x400m': ['400m', '400m', '400m', '400m'],
        '4x800m': ['800m', '800m', '800m', '800m'],
        'DMR': ['1200m', '400m', '800m', '1600m'],
        'SMR': ['400m', '200m', '200m', '800m'],
    }

    @staticmethod
    def insert_relay(data, legs):
        """Insert a relay team and its legs. Also inserts individual Results rows for backward compat."""
        conn = Database.get_connection()
        if not conn:
            raise Exception("Could not connect to database")
        try:
            with conn:
                cur = conn.cursor()
                # Compute total time from splits
                total_seconds = 0
                for leg in legs:
                    t = leg['split_result']
                    if ':' in t:
                        parts = t.split(':')
                        total_seconds += float(parts[0]) * 60 + float(parts[1])
                    else:
                        total_seconds += float(t)
                minutes = int(total_seconds // 60)
                seconds = total_seconds - minutes * 60
                total_result = f"{minutes}:{seconds:05.2f}"

                cur.execute(
                    'INSERT INTO RelayTeams (Date, Meet_Name, Team, Event, Total_Result, Team_Designation) VALUES (?, ?, ?, ?, ?, ?)',
                    (data['date'], data['meet'], data['team'], data['event'], total_result, data.get('team_designation', 'A'))
                )
                relay_id = cur.lastrowid

                for idx, leg in enumerate(legs, start=1):
                    leg_number = leg.get('leg_number', idx)
                    split_event = leg.get('split_event')
                    if not split_event and data.get('event') in RelayTeam.RELAY_CONFIG:
                        split_event = RelayTeam.RELAY_CONFIG[data['event']][idx - 1]
                    cur.execute(
                        'INSERT INTO RelayLegs (Relay_ID, Leg_Number, Athlete, Split_Event, Split_Result) VALUES (?, ?, ?, ?, ?)',
                        (relay_id, leg_number, leg['athlete'], split_event, leg['split_result'])
                    )
                    # Backward compat: also insert into Results so splits show on athlete profiles / meet pages
                    rs_event = f"{split_event} RS" if split_event else ""
                    cur.execute(
                        'INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team) VALUES (?, ?, ?, ?, ?, ?)',
                        (data['date'], leg['athlete'], data['meet'], rs_event, leg['split_result'], data['team'])
                    )
                conn.commit()
                return relay_id
        except Exception as e:
            raise Exception(f"Failed to insert relay: {str(e)}")
        finally:
            if conn:
                conn.close()

    @staticmethod
    def get_relays_for_meet(meet_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT Relay_ID, Date, Meet_Name, Team, Event, Total_Result, Team_Designation
                FROM RelayTeams
                WHERE Meet_Name = ?
                ORDER BY Event, Team, Team_Designation
            ''', (meet_name,))
            relays = cur.fetchall()
            result = []
            for relay in relays:
                relay_id = relay[0]
                cur.execute('''
                    SELECT Leg_Number, Athlete, Split_Event, Split_Result
                    FROM RelayLegs
                    WHERE Relay_ID = ?
                    ORDER BY Leg_Number
                ''', (relay_id,))
                legs = cur.fetchall()
                result.append({
                    'relay_id': relay_id,
                    'date': relay[1],
                    'meet': relay[2],
                    'team': relay[3],
                    'event': relay[4],
                    'total_result': relay[5],
                    'team_designation': relay[6],
                    'legs': [{'leg_number': l[0], 'athlete': l[1], 'split_event': l[2], 'split_result': l[3]} for l in legs]
                })
            return result

    @staticmethod
    def get_relays_for_athlete(athlete_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT rt.Relay_ID, rt.Date, rt.Meet_Name, rt.Team, rt.Event, rt.Total_Result, rt.Team_Designation
                FROM RelayTeams rt
                JOIN RelayLegs rl ON rt.Relay_ID = rl.Relay_ID
                WHERE rl.Athlete = ?
                ORDER BY rt.Date DESC
            ''', (athlete_name,))
            relays = cur.fetchall()
            result = []
            for relay in relays:
                relay_id = relay[0]
                cur.execute('''
                    SELECT Leg_Number, Athlete, Split_Event, Split_Result
                    FROM RelayLegs
                    WHERE Relay_ID = ?
                    ORDER BY Leg_Number
                ''', (relay_id,))
                legs = cur.fetchall()
                result.append({
                    'relay_id': relay_id,
                    'date': relay[1],
                    'meet': relay[2],
                    'team': relay[3],
                    'event': relay[4],
                    'total_result': relay[5],
                    'team_designation': relay[6],
                    'legs': [{'leg_number': l[0], 'athlete': l[1], 'split_event': l[2], 'split_result': l[3]} for l in legs]
                })
            return result

    @staticmethod
    def update_relay(relay_id, data, legs):
        """Update an existing relay team and its legs. Replaces all legs + backward-compat Results."""
        conn = Database.get_connection()
        if not conn:
            raise Exception("Could not connect to database")
        try:
            with conn:
                cur = conn.cursor()
                # Get old relay info for cleaning up backward-compat Results
                cur.execute('SELECT Date, Meet_Name, Team FROM RelayTeams WHERE Relay_ID = ?', (relay_id,))
                old = cur.fetchone()
                if not old:
                    raise Exception(f"Relay {relay_id} not found")
                old_date, old_meet, old_team = old['Date'], old['Meet_Name'], old['Team']

                # Delete old backward-compat Results by matching old relay data + legs
                cur.execute('SELECT Athlete, Split_Event FROM RelayLegs WHERE Relay_ID = ?', (relay_id,))
                for leg_row in cur.fetchall():
                    old_rs_event = f"{leg_row['Split_Event']} RS"
                    cur.execute(
                        'DELETE FROM Results WHERE Date=? AND Meet_Name=? AND Athlete=? AND Event=? AND Team=?',
                        (old_date, old_meet, leg_row['Athlete'], old_rs_event, old_team)
                    )

                # Compute total time from splits
                total_seconds = 0
                for leg in legs:
                    t = leg['split_result']
                    if ':' in t:
                        parts = t.split(':')
                        total_seconds += float(parts[0]) * 60 + float(parts[1])
                    else:
                        total_seconds += float(t)
                minutes = int(total_seconds // 60)
                seconds = total_seconds - minutes * 60
                total_result = f"{minutes}:{seconds:05.2f}"

                cur.execute(
                    'UPDATE RelayTeams SET Date=?, Meet_Name=?, Team=?, Event=?, Total_Result=?, Team_Designation=? WHERE Relay_ID=?',
                    (data['date'], data['meet'], data['team'], data['event'], total_result, data.get('team_designation', 'A'), relay_id)
                )

                # Delete old legs
                cur.execute('DELETE FROM RelayLegs WHERE Relay_ID = ?', (relay_id,))

                for idx, leg in enumerate(legs, start=1):
                    leg_number = leg.get('leg_number', idx)
                    split_event = leg.get('split_event')
                    if not split_event and data.get('event') in RelayTeam.RELAY_CONFIG:
                        split_event = RelayTeam.RELAY_CONFIG[data['event']][idx - 1]
                    cur.execute(
                        'INSERT INTO RelayLegs (Relay_ID, Leg_Number, Athlete, Split_Event, Split_Result) VALUES (?, ?, ?, ?, ?)',
                        (relay_id, leg_number, leg['athlete'], split_event, leg['split_result'])
                    )
                    # Backward compat: insert into Results
                    rs_event = f"{split_event} RS" if split_event else ""
                    cur.execute(
                        'INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team) VALUES (?, ?, ?, ?, ?, ?)',
                        (data['date'], leg['athlete'], data['meet'], rs_event, leg['split_result'], data['team'])
                    )
                conn.commit()
                return relay_id
        except Exception as e:
            raise Exception(f"Failed to update relay: {str(e)}")
        finally:
            if conn:
                conn.close()

    @staticmethod
    def delete_relay(relay_id):
        """Delete a relay team, its legs, and backward-compat Results rows."""
        conn = Database.get_connection()
        if not conn:
            raise Exception("Could not connect to database")
        try:
            with conn:
                cur = conn.cursor()
                # Get relay info and legs first so we can clean up backward-compat Results
                cur.execute('SELECT Date, Meet_Name, Team FROM RelayTeams WHERE Relay_ID = ?', (relay_id,))
                relay_row = cur.fetchone()
                if not relay_row:
                    raise Exception(f"Relay {relay_id} not found")
                relay_date, relay_meet, relay_team = relay_row['Date'], relay_row['Meet_Name'], relay_row['Team']

                cur.execute('SELECT Athlete, Split_Event FROM RelayLegs WHERE Relay_ID = ?', (relay_id,))
                for leg_row in cur.fetchall():
                    rs_event = f"{leg_row['Split_Event']} RS"
                    cur.execute(
                        'DELETE FROM Results WHERE Date=? AND Meet_Name=? AND Athlete=? AND Event=? AND Team=?',
                        (relay_date, relay_meet, leg_row['Athlete'], rs_event, relay_team)
                    )

                # Delete legs (ON DELETE CASCADE should handle this, but do it explicitly)
                cur.execute('DELETE FROM RelayLegs WHERE Relay_ID = ?', (relay_id,))
                # Delete relay team
                cur.execute('DELETE FROM RelayTeams WHERE Relay_ID = ?', (relay_id,))
                conn.commit()
                return True
        except Exception as e:
            raise Exception(f"Failed to delete relay: {str(e)}")
        finally:
            if conn:
                conn.close()

    @staticmethod
    def get_all_relay_events():
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT DISTINCT Event FROM RelayTeams')
            return [row[0] for row in cur.fetchall()]


def compute_stagger_deltas_for_meet(meet_name, get_placements_fn):
    """
    get_placements_fn(meet_name) -> dict: (event, date) -> list of dicts with 'athlete', 'place'.
    Each athlete's Elo result is averaged across their head-to-head matchups, so
    larger fields do not produce larger rating swings.
    Returns (all_deltas, display_changes). all_deltas = list of (event, date, athlete, delta).
    display_changes = list of (event, date, athlete, delta, new_score) for UI.
    """
    placements_by_key = get_placements_fn(meet_name)
    all_deltas = []
    display_changes = []

    # Use one connection for all rating lookups to avoid excessive connections / lock contention
    conn = Database.get_connection()
    try:
        with conn:
            cur = conn.cursor()
            for (event, date), records in placements_by_key.items():
                if not records:
                    continue
                # Ensure each athlete only appears once per event/date
                seen = set()
                unique_records = []
                for r in records:
                    a = r['athlete']
                    if a in seen:
                        continue
                    seen.add(a)
                    unique_records.append(r)
                athletes = [r['athlete'] for r in unique_records]

                ratings = {}
                for a in athletes:
                    cur.execute('SELECT score FROM StaggerScores WHERE athlete = ? AND event = ?', (a, event))
                    row = cur.fetchone()
                    ratings[a] = float(row[0]) if row else STAGGER_INITIAL

                matchup_deltas = {a: 0.0 for a in athletes}
                n = len(unique_records)
                for i in range(n):
                    for j in range(i + 1, n):
                        place_i = unique_records[i]['place']
                        place_j = unique_records[j]['place']
                        ai = unique_records[i]['athlete']
                        aj = unique_records[j]['athlete']
                        ri = ratings[ai]
                        rj = ratings[aj]
                        expected_i = _stagger_expected(ri, rj)
                        expected_j = 1.0 - expected_i
                        if place_i < place_j:
                            actual_i, actual_j = 1.0, 0.0
                        elif place_i > place_j:
                            actual_i, actual_j = 0.0, 1.0
                        else:
                            actual_i = actual_j = 0.5

                        matchup_deltas[ai] += actual_i - expected_i
                        matchup_deltas[aj] += actual_j - expected_j

                opponent_count = n - 1
                for athlete, matchup_delta in matchup_deltas.items():
                    delta = (
                        STAGGER_K * matchup_delta / opponent_count
                        if opponent_count
                        else 0.0
                    )
                    all_deltas.append((event, date, athlete, delta))
                    new_score = _stagger_dampen(ratings[athlete], delta)
                    display_changes.append((event, date, athlete, delta, new_score))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return all_deltas, display_changes
