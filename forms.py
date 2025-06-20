"""
forms.py

This file contains WTForms classes for handling user input in forms, including URL management, custom RSS feeds, and configuration settings.
"""

# Third-party imports
from wtforms import (BooleanField, FieldList, Form, FormField, IntegerField,
                     SelectField, StringField, TextAreaField, validators, PasswordField)


# Form for managing individual URLs.
class UrlForm(Form):
    pri = IntegerField('Priority')
    url = StringField(' ', render_kw={"readonly": True, "style": "width: 300px;"})

# Form for managing custom RSS feeds.
class CustomRSSForm(Form):
    pri = IntegerField('Priority')
    url = StringField(' ', render_kw={"style": "width: 300px;"}, validators=[validators.Length(min=10, max=120)])

# Form for managing overall configuration settings.
class ConfigForm(Form):
    delete_cookie = BooleanField(label="Delete cookies")
    no_underlines = BooleanField(label="No Underlines")
    headlines = TextAreaField(label="Headlines HTML", render_kw={"style": "width: 100%; height: 200px; font-family: monospace;"})
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))

# Form for login
class LoginForm(Form):
    username = StringField('Username', validators=[validators.DataRequired()], default='admin')
    password = PasswordField('Password', validators=[validators.DataRequired()])
    remember_me = BooleanField('Remember Me')