from flask_wtf import FlaskForm
from wtforms import SelectField, PasswordField, SubmitField, HiddenField
from wtforms.validators import DataRequired
from flask_login import UserMixin

class AdminUser(UserMixin):
    def __init__(self, id):
        self.id = id

class KnockForm(FlaskForm):
    duration = SelectField('Select Expiration', validators=[DataRequired()])
    submit = SubmitField('Knock Knock!')

    def __init__(self, expiration_choices=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.duration.choices = expiration_choices or [('1d','1 Day'),('1w','1 Week'),('1m','1 Month')]

class AdminLoginForm(FlaskForm):
    admin_password = PasswordField('Admin Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RevokeForm(FlaskForm):
    ip = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Revoke')

class ExtendForm(FlaskForm):
    ip = HiddenField(validators=[DataRequired()])
    duration = SelectField('Extend Duration', validators=[DataRequired()])
    submit = SubmitField('Extend')

    def __init__(self, expiration_choices=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.duration.choices = expiration_choices or [('1d','1 Day'),('1w','1 Week'),('1m','1 Month')]    
