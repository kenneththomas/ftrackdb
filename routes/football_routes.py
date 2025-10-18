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
            
            # For certain play types, use QB as player
            if form.play_type.data in ['Keep', 'Sack']:
                player_name = quarterback
            
            # For incomplete passes, receiver name is optional
            if form.play_type.data == 'Incomplete':
                player_name = player_name or 'N/A'
                is_complete = False
            else:
                is_complete = True
            
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
                                  quarterback=quarterback))
            
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
    
    plays = Play.get_game_plays(game_id)
    
    # Get team logos
    conn = Database.get_connection()
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT team_name, logo_url FROM Teams')
        team_logos = dict(cur.fetchall())
    
    return render_template('football_game.html', 
                         game=game, 
                         plays=plays,
                         team_logos=team_logos)

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

