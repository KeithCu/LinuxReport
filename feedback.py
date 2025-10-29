"""
feedback.py

Handles user feedback for LLM-generated headlines. Allows users to provide thumbs up/down feedback
on headlines, which can be used to improve AI model selection and prompt tuning.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import hashlib
import time
from datetime import datetime

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from flask import jsonify, request
from flask_restful import Resource

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import g_c, g_cm, EXPIRE_YEARS, limiter, dynamic_rate_limit, API, g_logger

# =============================================================================
# FEEDBACK CONSTANTS
# =============================================================================
FEEDBACK_KEY_PREFIX = "headline_feedback:"
FEEDBACK_STATS_KEY = "headline_feedback_stats"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_headline_hash(headline_url, headline_title):
    """
    Generate a consistent hash for a headline based on URL and title.
    
    Args:
        headline_url (str): The URL of the headline
        headline_title (str): The title of the headline
    
    Returns:
        str: MD5 hash of the headline identifier
    """
    identifier = f"{headline_url}:{headline_title}"
    return hashlib.md5(identifier.encode('utf-8')).hexdigest()

# =============================================================================
# FEEDBACK RESOURCES
# =============================================================================

class FeedbackResource(Resource):
    """
    Resource for handling POST requests to /api/feedback.
    Allows users to submit thumbs up/down feedback on headlines.
    """
    
    @limiter.limit(dynamic_rate_limit)
    def post(self):
        """
        Submit feedback for a headline.
        
        Expected JSON:
        {
            "headline_url": "https://example.com/article",
            "headline_title": "Article Title",
            "feedback": "up" or "down"
        }
        """
        try:
            data = request.get_json()
            headline_url = data.get('headline_url', '').strip()
            headline_title = data.get('headline_title', '').strip()
            feedback = data.get('feedback', '').strip().lower()
            
            if not headline_url or not headline_title:
                return {"error": "headline_url and headline_title are required"}, 400
            
            if feedback not in ['up', 'down']:
                return {"error": "feedback must be 'up' or 'down'"}, 400
            
            # Generate hash for this headline
            headline_hash = get_headline_hash(headline_url, headline_title)
            feedback_key = f"{FEEDBACK_KEY_PREFIX}{headline_hash}"
            
            # Get existing feedback for this headline
            existing_feedback = g_c.get(feedback_key) or {
                'up': 0,
                'down': 0,
                'last_updated': time.time()
            }
            
            # Update feedback count
            existing_feedback[feedback] += 1
            existing_feedback['last_updated'] = time.time()
            
            # Store feedback in disk cache (persistent)
            g_c.put(feedback_key, existing_feedback, timeout=EXPIRE_YEARS)
            
            # Update aggregate stats
            stats = g_c.get(FEEDBACK_STATS_KEY) or {
                'total_up': 0,
                'total_down': 0,
                'headlines_with_feedback': 0
            }
            stats['total_up'] += 1 if feedback == 'up' else 0
            stats['total_down'] += 1 if feedback == 'down' else 0
            stats['headlines_with_feedback'] = len([
                k for k in g_c.keys() if k.startswith(FEEDBACK_KEY_PREFIX)
            ])
            g_c.put(FEEDBACK_STATS_KEY, stats, timeout=EXPIRE_YEARS)
            
            g_logger.info(f"Feedback received: {feedback} for headline {headline_hash}")
            
            return {
                "success": True,
                "feedback": feedback,
                "counts": {
                    "up": existing_feedback['up'],
                    "down": existing_feedback['down']
                }
            }, 200
            
        except Exception as e:
            g_logger.error(f"Error processing feedback: {e}")
            return {"error": "Internal server error"}, 500

class FeedbackStatsResource(Resource):
    """
    Resource for handling GET requests to /api/feedback/stats.
    Provides feedback statistics for admin monitoring.
    """
    
    @limiter.limit(dynamic_rate_limit)
    def get(self):
        """
        Get feedback statistics.
        
        Returns aggregate statistics about headline feedback.
        """
        try:
            stats = g_c.get(FEEDBACK_STATS_KEY) or {
                'total_up': 0,
                'total_down': 0,
                'headlines_with_feedback': 0
            }
            
            # Get all feedback keys
            feedback_keys = [k for k in g_c.keys() if k.startswith(FEEDBACK_KEY_PREFIX)]
            
            return {
                "stats": stats,
                "total_headlines_with_feedback": len(feedback_keys),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }, 200
            
        except Exception as e:
            g_logger.error(f"Error fetching feedback stats: {e}")
            return {"error": "Internal server error"}, 500

class HeadlineFeedbackResource(Resource):
    """
    Resource for handling GET requests to /api/feedback/headline.
    Returns feedback for a specific headline.
    """
    
    @limiter.limit(dynamic_rate_limit)
    def get(self):
        """
        Get feedback for a specific headline.
        
        Query parameters:
        - headline_url: URL of the headline
        - headline_title: Title of the headline
        """
        try:
            headline_url = request.args.get('headline_url', '').strip()
            headline_title = request.args.get('headline_title', '').strip()
            
            if not headline_url or not headline_title:
                return {"error": "headline_url and headline_title are required"}, 400
            
            headline_hash = get_headline_hash(headline_url, headline_title)
            feedback_key = f"{FEEDBACK_KEY_PREFIX}{headline_hash}"
            
            feedback = g_c.get(feedback_key) or {
                'up': 0,
                'down': 0
            }
            
            return {
                "headline_url": headline_url,
                "headline_title": headline_title,
                "feedback": feedback
            }, 200
            
        except Exception as e:
            g_logger.error(f"Error fetching headline feedback: {e}")
            return {"error": "Internal server error"}, 500

# =============================================================================
# FEEDBACK ROUTE INITIALIZATION
# =============================================================================

def init_feedback_routes(app, limiter, dynamic_rate_limit):
    """
    Initializes all feedback-related routes for the Flask application using Flask-RESTful.
    
    Args:
        app (Flask): The Flask application instance.
        limiter (Flask-Limiter): The rate limiter instance.
        dynamic_rate_limit (function): Function to determine rate limit string.
    """
    # Register Flask-RESTful resources
    API.add_resource(FeedbackResource, '/api/feedback')
    API.add_resource(FeedbackStatsResource, '/api/feedback/stats')
    API.add_resource(HeadlineFeedbackResource, '/api/feedback/headline')

