"""
forms.py

Defines Flask-WTF form classes for handling user input across the application.
This includes forms for configuration management, user login, and managing RSS feed URLs.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
# (No standard library imports are needed in this file)

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    IntegerField,
    TextAreaField,
    FormField,
    FieldList,
    Form,
    validators
)

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
# (No local imports are needed in this file)

# =============================================================================
# FORM DEFINITIONS
# =============================================================================

class UrlForm(Form):
    """
    Form for managing an individual, existing RSS feed URL.
    Used within a FieldList in the main ConfigForm.
    """
    pri = IntegerField('Priority')
    url = StringField('URL', render_kw={"readonly": True, "style": "width: 300px;"})

class CustomRSSForm(Form):
    """
    Form for adding or editing a custom RSS feed URL.
    Used within a FieldList in the main ConfigForm.
    """
    pri = IntegerField('Priority')
    url = StringField(
        'URL',
        validators=[validators.Length(min=10, max=120)],
        render_kw={"style": "width: 300px;"}
    )

class ConfigForm(Form):
    """
    Main configuration form for the admin panel.
    Allows an admin to manage site settings, headlines, and RSS feeds.
    """
    delete_cookie = BooleanField(label="Delete cookies")
    no_underlines = BooleanField(label="No Underlines")
    headlines = TextAreaField(
        label="Headlines HTML",
        render_kw={"style": "width: 100%; height: 200px; font-family: monospace;"}
    )
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))

class LoginForm(Form):
    """
    Form for user authentication.
    """
    username = StringField('Username', validators=[validators.DataRequired()], default='admin')
    password = PasswordField('Password', validators=[validators.DataRequired()])
    remember_me = BooleanField('Remember Me')
