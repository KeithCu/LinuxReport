"""
test_forms.py

Tests for Flask-WTF form validation and CSRF protection.
"""

import pytest
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from forms import LoginForm, ConfigForm, CustomRSSForm, UrlForm


@pytest.fixture
def app():
    """Create a test Flask app with CSRF protection."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = True
    csrf = CSRFProtect()
    csrf.init_app(app)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


def test_login_form_validation():
    """Test LoginForm validation."""
    # Test valid form
    form = LoginForm()
    form.username.data = 'admin'
    form.password.data = 'password123'
    assert form.validate() is True
    
    # Test invalid form (empty username)
    form = LoginForm()
    form.username.data = ''
    form.password.data = 'password123'
    assert form.validate() is False
    assert 'Username is required' in str(form.username.errors)
    
    # Test invalid form (empty password)
    form = LoginForm()
    form.username.data = 'admin'
    form.password.data = ''
    assert form.validate() is False
    assert 'Password is required' in str(form.password.errors)


def test_custom_rss_form_validation():
    """Test CustomRSSForm validation."""
    # Test valid form
    form = CustomRSSForm()
    form.url.data = 'https://example.com/feed.xml'
    form.pri.data = 10
    assert form.validate() is True
    
    # Test invalid URL
    form = CustomRSSForm()
    form.url.data = 'not-a-url'
    form.pri.data = 10
    assert form.validate() is False
    assert 'Please enter a valid URL' in str(form.url.errors)
    
    # Test URL too short
    form = CustomRSSForm()
    form.url.data = 'http://a'
    form.pri.data = 10
    assert form.validate() is False
    assert 'URL must be between 10 and 120 characters' in str(form.url.errors)


def test_config_form_validation():
    """Test ConfigForm validation."""
    # Test valid form
    form = ConfigForm()
    form.headlines.data = '<h1>Test Headlines</h1>'
    form.no_underlines.data = True
    assert form.validate() is True
    
    # Test headlines too long
    form = ConfigForm()
    form.headlines.data = 'x' * 50001  # Over 50,000 character limit
    form.no_underlines.data = True
    assert form.validate() is False
    assert 'Headlines content is too long' in str(form.headlines.errors)


def test_csrf_protection_enabled(app):
    """Test that CSRF protection is properly enabled."""
    with app.test_request_context():
        form = LoginForm()
        # CSRF token should be present
        assert hasattr(form, 'csrf_token')
        assert form.csrf_token is not None


def test_form_field_rendering():
    """Test that form fields render properly."""
    form = LoginForm()
    # Test that fields have proper attributes
    assert form.username.label.text == 'Username'
    assert form.password.label.text == 'Password'
    assert form.remember_me.label.text == 'Remember Me' 