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
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    IntegerField,
    TextAreaField,
    FormField,
    FieldList,
    validators
)

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
# (No local imports are needed in this file)

# =============================================================================
# FORM DEFINITIONS
# =============================================================================

class UrlForm(FlaskForm):
    """
    Form for managing an individual, existing RSS feed URL.
    Used within a FieldList in the main ConfigForm.
    """
    pri = IntegerField('Priority', validators=[validators.Optional()])
    url = StringField('URL', render_kw={"readonly": True, "style": "width: 300px;"})

class CustomRSSForm(FlaskForm):
    """
    Form for adding or editing a custom RSS feed URL.
    Used within a FieldList in the main ConfigForm.
    """
    pri = IntegerField('Priority', validators=[validators.Optional()])
    url = StringField(
        'URL',
        validators=[
            validators.Length(min=10, max=120, message="URL must be between 10 and 120 characters"),
            validators.URL(message="Please enter a valid URL")
        ],
        render_kw={"style": "width: 300px;"}
    )

class ConfigForm(FlaskForm):
    """
    Main configuration form for the admin panel.
    Allows an admin to manage site settings, headlines, and RSS feeds.
    """
    delete_cookie = BooleanField(label="Delete cookies")
    no_underlines = BooleanField(label="No Underlines")
    headlines = TextAreaField(
        label="Headlines HTML",
        validators=[
            validators.Optional(),
            validators.Length(max=50000, message="Headlines content is too long (max 50,000 characters)")
        ],
        render_kw={"style": "width: 100%; height: 200px; font-family: monospace;"}
    )
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))

class LoginForm(FlaskForm):
    """
    Form for user authentication with CSRF protection.
    """
    username = StringField(
        'Username', 
        validators=[
            validators.DataRequired(message="Username is required"),
            validators.Length(min=1, max=50, message="Username must be between 1 and 50 characters")
        ], 
        default='admin'
    )
    password = PasswordField(
        'Password', 
        validators=[
            validators.DataRequired(message="Password is required"),
            validators.Length(min=1, max=100, message="Password must be between 1 and 100 characters")
        ]
    )
    remember_me = BooleanField('Remember Me')
