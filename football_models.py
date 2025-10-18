import sqlite3
from flask import current_app
from datetime import datetime

class FootballDatabase:
    @staticmethod
    def initialize_football_tables(conn):
        """Initialize football-specific tables"""
        try:
            cur = conn.cursor()
            
            # Games table - similar to Meets in track
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Games (
                    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    game_date DATE NOT NULL,
                    home_score INTEGER DEFAULT 0,
                    away_score INTEGER DEFAULT 0,
                    season_year INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(home_team, away_team, game_date)
                )
            ''')
            
            # Plays table - stores individual plays (passes, rushes, kicks)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS Plays (
                    play_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    play_type TEXT NOT NULL,
                    quarterback TEXT,
                    player_name TEXT NOT NULL,
                    team TEXT NOT NULL,
                    yards INTEGER DEFAULT 0,
                    is_touchdown INTEGER DEFAULT 0,
                    is_complete INTEGER DEFAULT 1,
                    is_successful INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES Games(game_id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
        except Exception as e:
            print(f"Error initializing football tables: {e}")

class Game:
    @staticmethod
    def get_or_create_game(home_team, away_team, game_date):
        """Get existing game or create new one, returns game_id"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            
            # Try to find existing game
            cur.execute('''
                SELECT game_id FROM Games 
                WHERE home_team = ? AND away_team = ? AND game_date = ?
            ''', (home_team, away_team, game_date))
            
            result = cur.fetchone()
            if result:
                return result[0]
            
            # Create new game
            season_year = datetime.strptime(game_date, '%Y-%m-%d').year
            cur.execute('''
                INSERT INTO Games (home_team, away_team, game_date, season_year)
                VALUES (?, ?, ?, ?)
            ''', (home_team, away_team, game_date, season_year))
            conn.commit()
            return cur.lastrowid
    
    @staticmethod
    def get_game_info(game_id):
        """Get game details"""
        from models import Database
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT game_id, home_team, away_team, 
                       strftime('%Y-%m-%d', game_date) as formatted_date,
                       home_score, away_score
                FROM Games WHERE game_id = ?
            ''', (game_id,))
            return cur.fetchone()
    
    @staticmethod
    def get_all_games(limit=50, offset=0):
        """Get all games, most recent first"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT game_id, home_team, away_team,
                       strftime('%Y-%m-%d', game_date) as formatted_date,
                       home_score, away_score
                FROM Games
                ORDER BY game_date DESC, game_id DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            return cur.fetchall()
    
    @staticmethod
    def get_team_games(team_name):
        """Get all games for a specific team"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT game_id, home_team, away_team,
                       strftime('%Y-%m-%d', game_date) as formatted_date,
                       home_score, away_score
                FROM Games
                WHERE home_team = ? OR away_team = ?
                ORDER BY game_date DESC
            ''', (team_name, team_name))
            return cur.fetchall()
    
    @staticmethod
    def update_score(game_id):
        """Recalculate and update game score based on plays"""
        from models import Database
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            
            # Get game info
            cur.execute('SELECT home_team, away_team FROM Games WHERE game_id = ?', (game_id,))
            game = cur.fetchone()
            if not game:
                return
            
            home_team, away_team = game[0], game[1]
            
            # Calculate scores from plays
            # TDs = 6 points, XPs and 2pt conversions handled separately
            cur.execute('''
                SELECT team, 
                       SUM(CASE WHEN is_touchdown = 1 THEN 6 ELSE 0 END) as td_points,
                       SUM(CASE WHEN play_type = 'XP' AND is_successful = 1 THEN 1 ELSE 0 END) as xp_points,
                       SUM(CASE WHEN play_type = 'FG' AND is_successful = 1 THEN 3 ELSE 0 END) as fg_points
                FROM Plays
                WHERE game_id = ?
                GROUP BY team
            ''', (game_id,))
            
            scores = {home_team: 0, away_team: 0}
            for row in cur.fetchall():
                team, td_points, xp_points, fg_points = row[0], row[1] or 0, row[2] or 0, row[3] or 0
                scores[team] = td_points + xp_points + fg_points
            
            # Update game scores
            cur.execute('''
                UPDATE Games 
                SET home_score = ?, away_score = ?
                WHERE game_id = ?
            ''', (scores[home_team], scores[away_team], game_id))
            conn.commit()
    
    @staticmethod
    def get_team_record(team_name, season_year=None):
        """Get team's win-loss record"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        if season_year is None:
            season_year = datetime.now().year
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT 
                    SUM(CASE 
                        WHEN (home_team = ? AND home_score > away_score) 
                          OR (away_team = ? AND away_score > home_score) THEN 1 
                        ELSE 0 
                    END) as wins,
                    SUM(CASE 
                        WHEN (home_team = ? AND home_score < away_score) 
                          OR (away_team = ? AND away_score < home_score) THEN 1 
                        ELSE 0 
                    END) as losses,
                    COUNT(*) as total_games
                FROM Games
                WHERE (home_team = ? OR away_team = ?)
                AND season_year = ?
            ''', (team_name, team_name, team_name, team_name, team_name, team_name, season_year))
            
            result = cur.fetchone()
            return {
                'wins': result[0] or 0,
                'losses': result[1] or 0,
                'total_games': result[2] or 0
            }
    
    @staticmethod
    def get_team_record_alltime(team_name):
        """Get team's all-time win-loss record"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT 
                    SUM(CASE 
                        WHEN (home_team = ? AND home_score > away_score) 
                          OR (away_team = ? AND away_score > home_score) THEN 1 
                        ELSE 0 
                    END) as wins,
                    SUM(CASE 
                        WHEN (home_team = ? AND home_score < away_score) 
                          OR (away_team = ? AND away_score < home_score) THEN 1 
                        ELSE 0 
                    END) as losses,
                    COUNT(*) as total_games
                FROM Games
                WHERE home_team = ? OR away_team = ?
            ''', (team_name, team_name, team_name, team_name, team_name, team_name))
            
            result = cur.fetchone()
            return {
                'wins': result[0] or 0,
                'losses': result[1] or 0,
                'total_games': result[2] or 0
            }

class Play:
    @staticmethod
    def add_play(game_id, play_type, player_name, team, yards=0, is_touchdown=False, 
                 quarterback=None, is_complete=True, is_successful=True):
        """Add a new play to the database"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO Plays (game_id, play_type, quarterback, player_name, team, 
                                   yards, is_touchdown, is_complete, is_successful)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, play_type, quarterback, player_name, team, yards, 
                  1 if is_touchdown else 0, 1 if is_complete else 0, 1 if is_successful else 0))
            conn.commit()
            play_id = cur.lastrowid
        
        # Update game score
        Game.update_score(game_id)
        return play_id
    
    @staticmethod
    def get_game_plays(game_id):
        """Get all plays for a specific game"""
        from models import Database
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT play_id, play_type, quarterback, player_name, team,
                       yards, is_touchdown, is_complete, is_successful,
                       strftime('%Y-%m-%d %H:%M:%S', created_at) as formatted_time
                FROM Plays
                WHERE game_id = ?
                ORDER BY play_id DESC
            ''', (game_id,))
            return cur.fetchall()
    
    @staticmethod
    def get_player_stats(player_name):
        """Get comprehensive stats for a player"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            
            # Passing stats
            cur.execute('''
                SELECT 
                    COUNT(*) as attempts,
                    SUM(CASE WHEN is_complete = 1 AND play_type = 'Pass' THEN 1 ELSE 0 END) as completions,
                    SUM(CASE WHEN play_type = 'Pass' THEN yards ELSE 0 END) as pass_yards,
                    SUM(CASE WHEN play_type = 'Pass' AND is_touchdown = 1 THEN 1 ELSE 0 END) as pass_tds
                FROM Plays
                WHERE quarterback = ? AND (play_type = 'Pass' OR play_type = 'Incomplete' OR play_type = 'Sack')
            ''', (player_name,))
            passing = cur.fetchone()
            
            # Rushing stats (including QB keeps)
            cur.execute('''
                SELECT 
                    COUNT(*) as carries,
                    SUM(yards) as rush_yards,
                    SUM(is_touchdown) as rush_tds
                FROM Plays
                WHERE player_name = ? AND (play_type = 'Rush' OR play_type = 'Keep')
            ''', (player_name,))
            rushing = cur.fetchone()
            
            # Receiving stats
            cur.execute('''
                SELECT 
                    COUNT(*) as receptions,
                    SUM(yards) as rec_yards,
                    SUM(is_touchdown) as rec_tds
                FROM Plays
                WHERE player_name = ? AND play_type = 'Pass' AND is_complete = 1
            ''', (player_name,))
            receiving = cur.fetchone()
            
            # Kicking stats
            cur.execute('''
                SELECT 
                    SUM(CASE WHEN play_type = 'FG' THEN 1 ELSE 0 END) as fg_attempts,
                    SUM(CASE WHEN play_type = 'FG' AND is_successful = 1 THEN 1 ELSE 0 END) as fg_made,
                    SUM(CASE WHEN play_type = 'XP' THEN 1 ELSE 0 END) as xp_attempts,
                    SUM(CASE WHEN play_type = 'XP' AND is_successful = 1 THEN 1 ELSE 0 END) as xp_made
                FROM Plays
                WHERE player_name = ?
            ''', (player_name,))
            kicking = cur.fetchone()
            
            return {
                'passing': passing,
                'rushing': rushing,
                'receiving': receiving,
                'kicking': kicking
            }
    
    @staticmethod
    def get_player_game_log(player_name):
        """Get game-by-game stats for a player"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT 
                    g.game_id,
                    g.home_team,
                    g.away_team,
                    strftime('%Y-%m-%d', g.game_date) as formatted_date,
                    g.home_score,
                    g.away_score,
                    p.team,
                    
                    -- Passing stats
                    SUM(CASE WHEN p.quarterback = ? AND (p.play_type IN ('Pass', 'Incomplete', 'Sack')) THEN 1 ELSE 0 END) as pass_attempts,
                    SUM(CASE WHEN p.quarterback = ? AND p.play_type = 'Pass' AND p.is_complete = 1 THEN 1 ELSE 0 END) as completions,
                    SUM(CASE WHEN p.quarterback = ? AND p.play_type = 'Pass' THEN p.yards ELSE 0 END) as pass_yards,
                    SUM(CASE WHEN p.quarterback = ? AND p.play_type = 'Pass' AND p.is_touchdown = 1 THEN 1 ELSE 0 END) as pass_tds,
                    
                    -- Rushing stats
                    SUM(CASE WHEN p.player_name = ? AND p.play_type IN ('Rush', 'Keep') THEN 1 ELSE 0 END) as carries,
                    SUM(CASE WHEN p.player_name = ? AND p.play_type IN ('Rush', 'Keep') THEN p.yards ELSE 0 END) as rush_yards,
                    SUM(CASE WHEN p.player_name = ? AND p.play_type IN ('Rush', 'Keep') AND p.is_touchdown = 1 THEN 1 ELSE 0 END) as rush_tds,
                    
                    -- Receiving stats
                    SUM(CASE WHEN p.player_name = ? AND p.play_type = 'Pass' AND p.is_complete = 1 THEN 1 ELSE 0 END) as receptions,
                    SUM(CASE WHEN p.player_name = ? AND p.play_type = 'Pass' AND p.is_complete = 1 THEN p.yards ELSE 0 END) as rec_yards,
                    SUM(CASE WHEN p.player_name = ? AND p.play_type = 'Pass' AND p.is_touchdown = 1 THEN 1 ELSE 0 END) as rec_tds
                    
                FROM Games g
                JOIN Plays p ON g.game_id = p.game_id
                WHERE p.player_name = ? OR p.quarterback = ?
                GROUP BY g.game_id
                ORDER BY g.game_date DESC
            ''', (player_name, player_name, player_name, player_name, 
                  player_name, player_name, player_name, 
                  player_name, player_name, player_name,
                  player_name, player_name))
            
            return cur.fetchall()
    
    @staticmethod
    def get_team_players(team_name):
        """Get all players who have played for a team"""
        from models import Database
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT DISTINCT player_name
                FROM Plays
                WHERE team = ?
                ORDER BY player_name
            ''', (team_name,))
            
            players = [row[0] for row in cur.fetchall()]
            
            # Also get QBs
            cur.execute('''
                SELECT DISTINCT quarterback
                FROM Plays
                WHERE team = ? AND quarterback IS NOT NULL
                ORDER BY quarterback
            ''', (team_name,))
            
            qbs = [row[0] for row in cur.fetchall()]
            
            # Combine and deduplicate
            all_players = list(set(players + qbs))
            all_players.sort()
            
            return all_players

