from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SubmitField, FormField, FieldList, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Length

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

class CommentForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=1, max=50)])
    content = TextAreaField('Comment', validators=[DataRequired(), Length(min=1, max=1000)])
    parent_id = HiddenField('Parent ID')
    submit = SubmitField('Post Comment') 