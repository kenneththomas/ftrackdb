from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SubmitField, FormField, FieldList
from wtforms.validators import DataRequired

class ResultForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    athlete = StringField('Athlete', validators=[DataRequired()])
    meet = StringField('Meet Name', validators=[DataRequired()])
    event = StringField('Event', validators=[DataRequired()])
    result = StringField('Result', validators=[DataRequired()])
    team = StringField('Team', validators=[DataRequired()])
    submit = SubmitField('Submit')

class SearchForm(FlaskForm):
    athlete = StringField('Athlete', validators=[DataRequired()])
    submit = SubmitField('Search')

class MeetResultForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    athlete = StringField('Athlete', validators=[DataRequired()])
    event = StringField('Event', validators=[DataRequired()])
    result = StringField('Result', validators=[DataRequired()])
    team = StringField('Team', validators=[DataRequired()])
    submit = SubmitField('Submit') 