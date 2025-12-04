from flask_wtf import FlaskForm
from wtforms import StringField, DateField, IntegerField, SelectField, BooleanField, SubmitField, ValidationError
from wtforms.validators import DataRequired, Optional
from datetime import date

class PlayForm(FlaskForm):
    # Game selection
    home_team = StringField('Home Team', validators=[DataRequired()])
    away_team = StringField('Away Team', validators=[DataRequired()])
    game_date = DateField('Game Date', validators=[DataRequired()], default=date.today)
    
    # Play details
    team = StringField('Offensive Team (Team with Possession)', validators=[DataRequired()])
    quarterback = StringField('Quarterback (QB)', validators=[Optional()])
    play_type = SelectField('Play Type', 
                           choices=[
                               ('', 'Select Play Type'),
                               ('Pass', 'Pass Play'),
                               ('Incomplete', 'Incomplete Pass'),
                               ('Rush', 'Rush Play'),
                               ('Keep', 'QB Keep'),
                               ('Sack', 'Sacked'),
                               ('FG', 'Field Goal'),
                               ('XP', 'Extra Point')
                           ],
                           validators=[DataRequired()])
    
    player_name = StringField('Player Involved', validators=[Optional()])
    yards = IntegerField('Yards', validators=[Optional()], default=0)
    is_touchdown = BooleanField('Touchdown')
    is_successful = BooleanField('Successful (for FG/XP)', default=True)
    
    submit = SubmitField('Add Play')
    
    def validate_quarterback(self, field):
        """Validate that quarterback is provided for play types that require it"""
        if self.play_type.data in ['Keep', 'Sack', 'Pass', 'Incomplete']:
            if not field.data or not field.data.strip():
                raise ValidationError(f'Quarterback is required for {self.play_type.data} plays')
    
    def validate_player_name(self, field):
        """Validate that player name is provided for play types that require it"""
        # For Keep and Sack, quarterback will be used as player_name (validated above)
        if self.play_type.data not in ['Keep', 'Sack', 'Incomplete']:
            if not field.data or not field.data.strip():
                raise ValidationError(f'Player name is required for {self.play_type.data} plays')

