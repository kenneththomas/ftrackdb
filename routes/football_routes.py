from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from football_forms import PlayForm
from football_models import Game, Play, FootballDatabase
from models import Database, Team
from datetime import date

football_bp = Blueprint('football', __name__, url_prefix='/football')

@football_bp.route('/')
def football_home():
    """Football homepage showing recent games"""
    page = request.args.get('page', 1, type=int)
    per_page = 25
    offset = (page - 1) * per_page
    
    games = Game.get_all_games(limit=per_page, offset=offset)
    
    # Get team logos
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    return render_template('football_home.html', 
                         games=games, 
                         team_logos=team_logos,
                         page=page)

@football_bp.route('/play_entry', methods=['GET', 'POST'])
def play_entry():
    """Play builder - main entry point for adding plays"""
    form = PlayForm()
    
    if form.validate_on_submit():
        try:
            # Get or create game
            game_id = Game.get_or_create_game(
                home_team=form.home_team.data,
                away_team=form.away_team.data,
                game_date=form.game_date.data.strftime('%Y-%m-%d')
            )
            
            # Determine player name based on play type
            player_name = form.player_name.data
            quarterback = form.quarterback.data
            
            # Server-side validation: For certain play types, QB is required
            if form.play_type.data in ['Keep', 'Sack']:
                if not quarterback or not quarterback.strip():
                    flash('Quarterback is required for Keep and Sack plays', 'error')
                    raise ValueError('Missing quarterback for Keep/Sack play')
                player_name = quarterback
            
            # For incomplete passes, receiver name is optional
            if form.play_type.data == 'Incomplete':
                player_name = player_name or 'N/A'
                is_complete = False
            else:
                is_complete = True
            
            # Final validation: ensure player_name is not None or empty
            if not player_name or not player_name.strip():
                flash('Player name cannot be empty', 'error')
                raise ValueError('Missing player name')
            
            # Add the play
            Play.add_play(
                game_id=game_id,
                play_type=form.play_type.data,
                player_name=player_name,
                team=form.team.data,
                yards=form.yards.data or 0,
                is_touchdown=form.is_touchdown.data,
                quarterback=quarterback if form.play_type.data not in ['FG', 'XP'] else None,
                is_complete=is_complete,
                is_successful=form.is_successful.data
            )
            
            flash('Play added successfully!', 'success')
            
            # Redirect back to form with game info preserved
            return redirect(url_for('football.play_entry',
                                  home_team=form.home_team.data,
                                  away_team=form.away_team.data,
                                  game_date=form.game_date.data.strftime('%Y-%m-%d'),
                                  quarterback=quarterback,
                                  team=form.team.data))
            
        except Exception as e:
            flash(f'Error adding play: {str(e)}', 'error')
    
    # Pre-fill form from query parameters
    if request.args.get('home_team'):
        form.home_team.data = request.args.get('home_team')
    if request.args.get('away_team'):
        form.away_team.data = request.args.get('away_team')
    if request.args.get('game_date'):
        form.game_date.data = date.fromisoformat(request.args.get('game_date'))
    if request.args.get('quarterback'):
        form.quarterback.data = request.args.get('quarterback')
    if request.args.get('team'):
        form.team.data = request.args.get('team')
    
    # Get team logos for display
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    return render_template('play_entry.html', form=form, team_logos=team_logos)

@football_bp.route('/game/<int:game_id>')
def view_game(game_id):
    """View a specific game with all its plays"""
    game = Game.get_game_info(game_id)
    if not game:
        flash('Game not found', 'error')
        return redirect(url_for('football.football_home'))
    
    # Pagination for plays
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    plays = Play.get_game_plays(game_id, limit=per_page, offset=offset)
    total_plays = Play.get_game_plays_count(game_id)
    total_pages = (total_plays + per_page - 1) // per_page  # Ceiling division
    
    player_stats = Play.get_game_player_stats(game_id)
    
    # Get team logos
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    return render_template('football_game.html', 
                         game=game, 
                         plays=plays,
                         player_stats=player_stats,
                         team_logos=team_logos,
                         page=page,
                         total_pages=total_pages,
                         total_plays=total_plays)

@football_bp.route('/player/<player_name>')
def view_player(player_name):
    """View player profile with stats"""
    stats = Play.get_player_stats(player_name)
    game_log = Play.get_player_game_log(player_name)
    
    # Calculate games played
    games_played = len(game_log)
    
    # Calculate per-game averages
    averages = {}
    if games_played > 0:
        passing = stats['passing']
        rushing = stats['rushing']
        receiving = stats['receiving']
        
        if passing and passing[0]:  # Has passing stats
            averages['pass_yards_per_game'] = round((passing[2] or 0) / games_played, 1)
            averages['completion_pct'] = round(((passing[1] or 0) / passing[0] * 100), 1) if passing[0] else 0
        
        if rushing and rushing[1]:  # Has rushing yards
            averages['rush_yards_per_game'] = round((rushing[1] or 0) / games_played, 1)
        
        if receiving and receiving[1]:  # Has receiving yards
            averages['rec_yards_per_game'] = round((receiving[1] or 0) / games_played, 1)
    
    return render_template('football_player.html',
                         player_name=player_name,
                         stats=stats,
                         game_log=game_log,
                         games_played=games_played,
                         averages=averages)

@football_bp.route('/team/<team_name>')
def view_team(team_name):
    """View team profile with record and games"""
    from datetime import datetime
    
    games = Game.get_team_games(team_name)
    season_record = Game.get_team_record(team_name, datetime.now().year)
    alltime_record = Game.get_team_record_alltime(team_name)
    
    # Get team logo
    team_info = Team.get_team_info(team_name)
    
    # Get team roster
    players = Play.get_team_players(team_name)
    
    return render_template('football_team.html',
                         team_name=team_name,
                         games=games,
                         season_record=season_record,
                         alltime_record=alltime_record,
                         team_info=team_info,
                         players=players)

# API endpoints for autocomplete
@football_bp.route('/api/team_players/<team_name>')
def api_team_players(team_name):
    """Get all players for a team (for autocomplete)"""
    try:
        players = Play.get_team_players(team_name)
        return jsonify({'players': players})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@football_bp.route('/api/recent_quarterback')
def api_recent_quarterback():
    """Get the most recent quarterback from recent plays"""
    try:
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT quarterback 
                FROM Plays 
                WHERE quarterback IS NOT NULL 
                ORDER BY play_id DESC 
                LIMIT 1
            ''')
            result = cur.fetchone()
            return jsonify({'quarterback': result[0] if result else ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@football_bp.route('/api/teams')
def api_teams():
    """Get all teams that have played football"""
    try:
        conn = Database.get_connection()
        FootballDatabase.initialize_football_tables(conn)
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT DISTINCT home_team as team FROM Games
                UNION
                SELECT DISTINCT away_team as team FROM Games
                ORDER BY team
            ''')
            teams = [row[0] for row in cur.fetchall()]
            return jsonify({'teams': teams})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@football_bp.route('/api/game_players')
def api_game_players():
    """Get historical players from a team who have performed a specific action (position-based)"""
    try:
        home_team = request.args.get('home_team')
        away_team = request.args.get('away_team')
        game_date = request.args.get('game_date')
        play_type = request.args.get('play_type')
        team = request.args.get('team')
        
        # Only require team and play_type for historical lookup
        if not team or not play_type:
            return jsonify({'players': []})
        
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            
            # Special case for quarterbacks - get all QBs who have played for this team
            if play_type == 'QB':
                cur.execute('''
                    SELECT DISTINCT quarterback 
                    FROM Plays 
                    WHERE team = ?
                    AND quarterback IS NOT NULL
                    ORDER BY quarterback
                ''', (team,))
                
                players = [row[0] for row in cur.fetchall()]
                return jsonify({'players': players})
            
            # Get players based on play type - historical data for this team
            play_type_map = {
                'Pass': ['Pass'],
                'Rush': ['Rush'],
                'FG': ['FG'],
                'XP': ['XP'],
                'Keep': ['Keep'],
                'Sack': ['Sack']
            }
            
            if play_type not in play_type_map:
                return jsonify({'players': []})
            
            # Query for historical players who have done this action for this team
            cur.execute('''
                SELECT DISTINCT player_name 
                FROM Plays 
                WHERE play_type IN ({})
                AND team = ?
                AND player_name IS NOT NULL
                AND player_name != 'N/A'
                ORDER BY player_name
            '''.format(','.join('?' * len(play_type_map[play_type]))), 
                (*play_type_map[play_type], team))
            
            players = [row[0] for row in cur.fetchall()]
            return jsonify({'players': players})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@football_bp.route('/play/<int:play_id>/delete', methods=['POST'])
def delete_play(play_id):
    """Delete a specific play"""
    try:
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            
            # Get the game_id before deleting
            cur.execute('SELECT game_id FROM Plays WHERE play_id = ?', (play_id,))
            result = cur.fetchone()
            if not result:
                flash('Play not found', 'error')
                return redirect(url_for('football.football_home'))
            
            game_id = result[0]
            
            # Delete the play
            cur.execute('DELETE FROM Plays WHERE play_id = ?', (play_id,))
            conn.commit()
        
        # Update game score
        Game.update_score(game_id)
        
        flash('Play deleted successfully!', 'success')
        return redirect(url_for('football.view_game', game_id=game_id))
    except Exception as e:
        flash(f'Error deleting play: {str(e)}', 'error')
        return redirect(url_for('football.football_home'))

@football_bp.route('/play/<int:play_id>/edit', methods=['GET', 'POST'])
def edit_play(play_id):
    """Edit a specific play"""
    conn = Database.get_connection()
    
    # Get the play details
    with conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT p.play_id, p.game_id, p.play_type, p.quarterback, p.player_name, 
                   p.team, p.yards, p.is_touchdown, p.is_complete, p.is_successful,
                   g.home_team, g.away_team, g.game_date
            FROM Plays p
            JOIN Games g ON p.game_id = g.game_id
            WHERE p.play_id = ?
        ''', (play_id,))
        play = cur.fetchone()
        
        if not play:
            flash('Play not found', 'error')
            return redirect(url_for('football.football_home'))
    
    form = PlayForm()
    
    if form.validate_on_submit():
        try:
            # Determine player name based on play type
            player_name = form.player_name.data
            quarterback = form.quarterback.data
            
            # Server-side validation: For certain play types, QB is required
            if form.play_type.data in ['Keep', 'Sack']:
                if not quarterback or not quarterback.strip():
                    flash('Quarterback is required for Keep and Sack plays', 'error')
                    raise ValueError('Missing quarterback for Keep/Sack play')
                player_name = quarterback
            
            # For incomplete passes, receiver name is optional
            if form.play_type.data == 'Incomplete':
                player_name = player_name or 'N/A'
                is_complete = False
            else:
                is_complete = True
            
            # Final validation: ensure player_name is not None or empty
            if not player_name or not player_name.strip():
                flash('Player name cannot be empty', 'error')
                raise ValueError('Missing player name')
            
            # Update the play
            with conn:
                cur = conn.cursor()
                cur.execute('''
                    UPDATE Plays 
                    SET play_type = ?, quarterback = ?, player_name = ?, 
                        team = ?, yards = ?, is_touchdown = ?, 
                        is_complete = ?, is_successful = ?
                    WHERE play_id = ?
                ''', (form.play_type.data, 
                      quarterback if form.play_type.data not in ['FG', 'XP'] else None,
                      player_name, 
                      form.team.data, 
                      form.yards.data or 0,
                      1 if form.is_touchdown.data else 0,
                      1 if is_complete else 0,
                      1 if form.is_successful.data else 0,
                      play_id))
                conn.commit()
            
            # Update game score
            Game.update_score(play[1])
            
            flash('Play updated successfully!', 'success')
            return redirect(url_for('football.view_game', game_id=play[1]))
            
        except Exception as e:
            flash(f'Error updating play: {str(e)}', 'error')
    
    # Pre-fill form with existing play data
    if request.method == 'GET':
        form.home_team.data = play[10]
        form.away_team.data = play[11]
        form.game_date.data = date.fromisoformat(play[12])
        form.play_type.data = play[2]
        form.quarterback.data = play[3]
        form.player_name.data = play[4]
        form.team.data = play[5]
        form.yards.data = play[6]
        form.is_touchdown.data = bool(play[7])
        form.is_successful.data = bool(play[9])
    
    # Get team logos for display
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    return render_template('play_entry.html', form=form, team_logos=team_logos, 
                         edit_mode=True, play_id=play_id, game_id=play[1])

@football_bp.route('/api/add_incomplete_pass', methods=['POST'])
def add_incomplete_pass():
    """Quick add incomplete pass(es) for a QB"""
    try:
        data = request.get_json()
        game_id = data.get('game_id')
        quarterback = data.get('quarterback')
        team = data.get('team')
        count = data.get('count', 1)  # Default to 1 if not specified
        
        if not all([game_id, quarterback, team]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Validate count is a positive integer
        try:
            count = int(count)
            if count < 1:
                return jsonify({'error': 'Count must be a positive number'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid count value'}), 400
        
        # Add incomplete pass play(s)
        for _ in range(count):
            Play.add_play(
                game_id=game_id,
                play_type='Incomplete',
                player_name='N/A',
                team=team,
                yards=0,
                is_touchdown=False,
                quarterback=quarterback,
                is_complete=False,
                is_successful=True
            )
        
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

