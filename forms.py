"""
forms.py

This file contains WTForms classes for handling user input in forms, including URL management, custom RSS feeds, and configuration settings.
"""

# Third-party imports
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, SelectField, validators

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
        ('dark','Dark'),
        ('solarized','Solarized'),
        ('futuristic','Futuristic'),
        ('steampunk','Steampunk'),
        ('cyberpunk','Cyberpunk'),
        ('silver','Silver'),
        ('pastelle','Pastelle'),
        ('sepia','Sepia'),
        ('forest','Forest'),
    ])
    no_underlines = BooleanField(label="No Underlines")
    sans_serif = BooleanField(label="Sans Serif Font")
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))