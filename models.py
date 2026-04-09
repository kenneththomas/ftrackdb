import sqlite3
from sqlite3 import Error
from flask import current_app

class Database:
    @staticmethod
    def get_connection():
        conn = None
        try:
            # timeout helps prevent "database is locked" on rapid successive writes
            conn = sqlite3.connect(current_app.config['DATABASE'], timeout=30)
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
            # For field events (higher is better). Ft-in (e.g. 20'0") must be ranked in Python.
            else:
                cur.execute('''
                    SELECT Athlete, Result FROM Results
                    WHERE Event = ? AND Date <= ? AND Date >= ?
                ''', (event, target_date, one_year_ago))
                rows = cur.fetchall()
                result_strs = [r[1] for r in rows]
                from utils.field_utils import all_results_are_field_format, parse_field_result
                from collections import defaultdict
                if result_strs and all_results_are_field_format(result_strs):
                    by_athlete = defaultdict(list)
                    for athlete, result in rows:
                        by_athlete[athlete].append(result)
                    best_per_athlete = [(athlete, max(results, key=parse_field_result)) for athlete, results in by_athlete.items()]
                    best_per_athlete.sort(key=lambda x: parse_field_result(x[1]), reverse=True)
                    return {athlete: rank for rank, (athlete, _) in enumerate(best_per_athlete, start=1)}
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
                    # Convert time strings to numeric values for proper sorting
                    cur.execute('''
                        WITH BestResults AS (
                            SELECT 
                                Athlete,
                                Result,
                                CASE 
                                    WHEN Result LIKE '%:%' THEN
                                        CAST(SUBSTR(Result, 1, INSTR(Result, ':') - 1) AS REAL) * 60 +
                                        CAST(SUBSTR(Result, INSTR(Result, ':') + 1) AS REAL)
                                    ELSE
                                        CAST(Result AS REAL)
                                END as numeric_result
                            FROM Results 
                            WHERE Event = ? 
                            AND Date >= ?
                        ),
                        AthletePRs AS (
                            SELECT 
                                Athlete,
                                MIN(numeric_result) as best_result,
                                MIN(Result) as best_result_str
                            FROM BestResults
                            GROUP BY Athlete
                        ),
                        RankedResults AS (
                            SELECT 
                                Athlete,
                                best_result_str as Result,
                                ROW_NUMBER() OVER (ORDER BY best_result ASC) as rank
                            FROM AthletePRs
                        )
                        SELECT rank 
                        FROM RankedResults
                        WHERE Athlete = ?
                    ''', (event, one_year_ago, athlete_name))
                # For field events (higher is better)
                else:
                    cur.execute('''
                        WITH BestResults AS (
                            SELECT 
                                Athlete,
                                Result,
                                CAST(Result AS REAL) as numeric_result
                            FROM Results 
                            WHERE Event = ? 
                            AND Date >= ?
                            AND Result GLOB '[0-9]*.[0-9]*'
                        ),
                        AthletePRs AS (
                            SELECT 
                                Athlete,
                                MAX(numeric_result) as best_result,
                                MAX(Result) as best_result_str
                            FROM BestResults
                            GROUP BY Athlete
                        ),
                        RankedResults AS (
                            SELECT 
                                Athlete,
                                best_result_str as Result,
                                ROW_NUMBER() OVER (ORDER BY best_result DESC) as rank
                            FROM AthletePRs
                        )
                        SELECT rank 
                        FROM RankedResults
                        WHERE Athlete = ?
                    ''', (event, one_year_ago, athlete_name))
                
                result = cur.fetchone()
                if result:
                    rankings[event] = result[0]
            
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

    @staticmethod
    def delete_post(post_id):
        """Delete a board post and all its replies (CASCADE in DB)."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM BoardPosts WHERE id = ?', (post_id,))
            conn.commit()


# --- Stagger (ELO-style placement ranking) ---
STAGGER_K = 24
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


class StaggerScore:
    @staticmethod
    def get_score(athlete, event):
        """Return current stagger score for (athlete, event), or STAGGER_INITIAL if none."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT score FROM StaggerScores WHERE athlete = ? AND event = ?',
                (athlete, event)
            )
            row = cur.fetchone()
            return float(row[0]) if row else STAGGER_INITIAL

    @staticmethod
    def get_score_if_exists(athlete, event):
        """Return current stagger score for (athlete, event), or None if no score exists yet."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT score FROM StaggerScores WHERE athlete = ? AND event = ?',
                (athlete, event)
            )
            row = cur.fetchone()
            return float(row[0]) if row else None

    @staticmethod
    def get_scores_for_athlete(athlete):
        """Return dict event -> score for an athlete."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT event, score FROM StaggerScores WHERE athlete = ?',
                (athlete,)
            )
            return {row[0]: float(row[1]) for row in cur.fetchall()}

    @staticmethod
    def set_score(athlete, event, score):
        """Insert or update a single (athlete, event) score."""
        conn = Database.get_connection()
        try:
            with conn:
                cur = conn.cursor()
                clamped = max(STAGGER_FLOOR, min(STAGGER_CEILING, score))
                cur.execute('''
                    INSERT INTO StaggerScores (athlete, event, score)
                    VALUES (?, ?, ?)
                    ON CONFLICT(athlete, event) DO UPDATE SET score = excluded.score
                ''', (athlete, event, clamped))
                conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def get_meet_history(meet_name):
        """Return list of (event, date, athlete, delta) for a meet."""
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT event, date, athlete, delta
                FROM StaggerHistory
                WHERE meet_name = ?
                ORDER BY event, date, athlete
            ''', (meet_name,))
            return cur.fetchall()

    @staticmethod
    def revert_meet(meet_name):
        """Subtract stored deltas from StaggerScores and delete StaggerHistory for this meet."""
        conn = Database.get_connection()
        try:
            with conn:
                cur = conn.cursor()
                # Acquire write lock early to avoid partial updates
                cur.execute('BEGIN IMMEDIATE')
                cur.execute(
                    'SELECT event, athlete, delta FROM StaggerHistory WHERE meet_name = ?',
                    (meet_name,)
                )
                rows = cur.fetchall()
                for event, athlete, delta in rows:
                    cur.execute(
                        'SELECT score FROM StaggerScores WHERE athlete = ? AND event = ?',
                        (athlete, event)
                    )
                    row = cur.fetchone()
                    current = float(row[0]) if row else STAGGER_INITIAL
                    new_score = max(STAGGER_FLOOR, min(STAGGER_CEILING, current - float(delta)))
                    cur.execute('''
                        INSERT INTO StaggerScores (athlete, event, score)
                        VALUES (?, ?, ?)
                        ON CONFLICT(athlete, event) DO UPDATE SET score = excluded.score
                    ''', (athlete, event, new_score))
                cur.execute('DELETE FROM StaggerHistory WHERE meet_name = ?', (meet_name,))
                conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def apply_meet_deltas(meet_name, deltas):
        """deltas = list of (event, date, athlete, delta). Update StaggerScores and insert StaggerHistory."""
        conn = Database.get_connection()
        try:
            with conn:
                cur = conn.cursor()
                # Acquire write lock early to avoid partial updates
                cur.execute('BEGIN IMMEDIATE')
                for event, date, athlete, delta in deltas:
                    cur.execute(
                        'SELECT score FROM StaggerScores WHERE athlete = ? AND event = ?',
                        (athlete, event)
                    )
                    row = cur.fetchone()
                    current = float(row[0]) if row else STAGGER_INITIAL
                    new_score = _stagger_dampen(current, float(delta))
                    cur.execute('''
                        INSERT INTO StaggerScores (athlete, event, score)
                        VALUES (?, ?, ?)
                        ON CONFLICT(athlete, event) DO UPDATE SET score = excluded.score
                    ''', (athlete, event, new_score))
                    # Use INSERT OR REPLACE for safety (PK prevents duplicates anyway)
                    cur.execute('''
                        INSERT OR REPLACE INTO StaggerHistory (meet_name, event, date, athlete, delta)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (meet_name, event, date, athlete, delta))
                conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass


def compute_stagger_deltas_for_meet(meet_name, get_placements_fn):
    """
    get_placements_fn(meet_name) -> dict: (event, date) -> list of dicts with 'athlete', 'place'.
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

                deltas = {a: 0.0 for a in athletes}
                n = len(unique_records)
                for i in range(n):
                    for j in range(n):
                        if i == j:
                            continue
                        place_i = unique_records[i]['place']
                        place_j = unique_records[j]['place']
                        ai = unique_records[i]['athlete']
                        aj = unique_records[j]['athlete']
                        ri = ratings[ai]
                        rj = ratings[aj]
                        if place_i < place_j:
                            e_i = _stagger_expected(ri, rj)
                            e_j = 1.0 - e_i
                            deltas[ai] += STAGGER_K * (1.0 - e_i)
                            deltas[aj] += STAGGER_K * (0.0 - e_j)
                        elif place_i > place_j:
                            e_j = _stagger_expected(rj, ri)
                            e_i = 1.0 - e_j
                            deltas[aj] += STAGGER_K * (1.0 - e_j)
                            deltas[ai] += STAGGER_K * (0.0 - e_i)
                        else:
                            e_i = _stagger_expected(ri, rj)
                            e_j = 1.0 - e_i
                            deltas[ai] += STAGGER_K * (0.5 - e_i)
                            deltas[aj] += STAGGER_K * (0.5 - e_j)

                for athlete, delta in deltas.items():
                    all_deltas.append((event, date, athlete, delta))
                    new_score = _stagger_dampen(ratings[athlete], delta)
                    display_changes.append((event, date, athlete, delta, new_score))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return all_deltas, display_changes