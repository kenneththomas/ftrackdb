from flask_wtf import FlaskForm
from wtforms import StringField, DateField, IntegerField, SelectField, BooleanField, SubmitField
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

