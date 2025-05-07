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
    theme = SelectField(label="Theme", choices=[
        ('light','Light'),
        ('paper','Paper'),
        ('terminal','Terminal'),
        ('neon','Neon'),
        ('retro','Retro'),
        ('dark','Dark'),
        ('monokai','Monokai'),
        ('futuristic','Futuristic'),
        ('cyberpunk','Cyberpunk'),
        ('midnight','Midnight'),
        ('ocean','Ocean'),
        ('nord','Nord'),
        ('forest','Forest'),
        ('steampunk','Steampunk'),
        ('autumn','Autumn'),
        ('sepia','Sepia'),
        ('silver','Silver'),
        ('solarized','Solarized'),
        ('pastelle','Pastelle'),
    ])
    font_family = SelectField(label="Font", choices=[
        ('system', 'System Default (Serif)'),
        ('sans-serif', 'Sans Serif'),
        ('monospace', 'Monospace (Drudge-style)'),
        ('inter', 'Inter (Modern)'),
        ('roboto', 'Roboto (Clean)'),
        ('open-sans', 'Open Sans (Readable)'),
        ('source-sans', 'Source Sans Pro (Professional)'),
        ('noto-sans', 'Noto Sans (Universal)'),
        ('lato', 'Lato (Elegant)'),
        ('raleway', 'Raleway (Stylish)'),
    ])
    no_underlines = BooleanField(label="No Underlines")
    admin_mode = BooleanField(label="Enable Admin Mode", default=False)
    admin_password = PasswordField(label="Admin Password", validators=[validators.Optional()])
    headlines = TextAreaField(label="Headlines HTML", render_kw={"style": "width: 100%; height: 200px; font-family: monospace;"})
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))