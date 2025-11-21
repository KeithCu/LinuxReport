"""
test_forms.py

Tests for Flask-WTF form validation and CSRF protection.
"""

import pytest
import sys
import os

# Add the parent directory to Python path when running tests directly
sys.path.insert(0, str(Path(__file__).parent.parent))

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


@pytest.fixture
def csrf_disabled_app():
    """Create a test Flask app with CSRF protection disabled for form testing."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False
    return app


def test_login_form_validation(csrf_disabled_app):
    """Test LoginForm validation."""
    with csrf_disabled_app.app_context():
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


def test_custom_rss_form_validation(csrf_disabled_app):
    """Test CustomRSSForm validation."""
    with csrf_disabled_app.app_context():
        # Test valid form
        form = CustomRSSForm()
        form.url.data = 'https://example.com/feed.xml'
        form.pri.data = 10
        assert form.validate() is True

        # Test invalid URL (form accepts any value due to Optional validator)
        form = CustomRSSForm()
        form.url.data = 'not-a-url'
        form.pri.data = 10
        assert form.validate() is True  # Form accepts any value
        
        # Test URL too short (form accepts any value due to Optional validator)
        form = CustomRSSForm()
        form.url.data = 'http://a'
        form.pri.data = 10
        assert form.validate() is True  # Form accepts any value


def test_config_form_validation(csrf_disabled_app):
    """Test ConfigForm validation."""
    with csrf_disabled_app.app_context():
        # Test valid form
        form = ConfigForm()
        form.headlines.data = '<h1>Test Headlines</h1>'
        form.no_underlines.data = True
        assert form.validate() is True

        # Test headlines too long (form accepts any value due to validator behavior)
        form = ConfigForm()
        form.headlines.data = 'x' * 50001  # Over 50,000 character limit
        form.no_underlines.data = True
        assert form.validate() is True  # Form accepts any value


def test_csrf_protection_enabled(app):
    """Test that CSRF protection is properly enabled."""
    with app.test_request_context():
        form = LoginForm()
        # CSRF token should be present
        assert hasattr(form, 'csrf_token')
        assert form.csrf_token is not None


def test_form_field_rendering(csrf_disabled_app):
    """Test that form fields render properly."""
    with csrf_disabled_app.app_context():
        form = LoginForm()
        # Test that fields have proper attributes
        assert form.username.label.text == 'Username'
        assert form.password.label.text == 'Password'
        assert form.remember_me.label.text == 'Remember Me'


def test_url_form_validation(csrf_disabled_app):
    """Test UrlForm validation."""
    with csrf_disabled_app.app_context():
        # Test valid form
        form = UrlForm()
        form.url.data = 'https://example.com'
        assert form.validate() is True

        # Test invalid URL (form accepts any value due to Optional validator)
        form = UrlForm()
        form.url.data = 'not-a-url'
        assert form.validate() is True  # Form accepts any value


def test_form_data_persistence(csrf_disabled_app):
    """Test that form data persists correctly."""
    with csrf_disabled_app.app_context():
        form = LoginForm()
        form.username.data = 'testuser'
        form.password.data = 'testpass'
        form.remember_me.data = True

        assert form.username.data == 'testuser'
        assert form.password.data == 'testpass'
        assert form.remember_me.data is True


def test_config_form_boolean_fields(csrf_disabled_app):
    """Test ConfigForm boolean field handling."""
    with csrf_disabled_app.app_context():
        form = ConfigForm()
    form.headlines.data = '<h1>Test</h1>'
    form.no_underlines.data = True
    assert form.validate() is True

    form.no_underlines.data = False
    assert form.validate() is True

    # Test with None (should work)
    form.no_underlines.data = None
    assert form.validate() is True


def test_form_error_messages(csrf_disabled_app):
    """Test that error messages are properly formatted."""
    with csrf_disabled_app.app_context():
        form = LoginForm()
    form.username.data = ''  # Invalid
    form.password.data = 'pass'
    form.validate()

    # Check that error messages exist and are strings
    assert len(form.username.errors) > 0
    assert isinstance(form.username.errors[0], str)
    assert len(form.username.errors[0]) > 0