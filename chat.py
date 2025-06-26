"""
chat.py

Handles all chat-related functionality, including fetching, posting, and deleting comments,
as well as image uploads and real-time comment streaming via Server-Sent Events (SSE).
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import json
import uuid
import html
import datetime
import time

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from flask import jsonify, Response, request
from flask_login import login_required
from flask_restful import Resource, reqparse
from werkzeug.utils import secure_filename

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import get_chat_cache, get_ip_prefix, PATH, API, limiter, dynamic_rate_limit

# =============================================================================
# CHAT CONSTANTS
# =============================================================================
MAX_COMMENTS = 1000
COMMENTS_KEY = "chat_comments"
BANNED_IPS_KEY = "banned_ips"
WEB_UPLOAD_PATH = '/static/uploads'
UPLOAD_FOLDER = os.path.join(PATH, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def allowed_file(filename):
    """
    Checks if a given filename has an allowed image extension.

    Args:
        filename (str): The name of the file to check.

    Returns:
        bool: True if the file extension is allowed, False otherwise.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =============================================================================
# CHAT ROUTE INITIALIZATION
# =============================================================================

class CommentsResource(Resource):
    """
    Resource for handling GET and POST requests to /api/comments.
    """
    
    def get(self):
        """
        Fetches and returns all chat comments from the cache.
        Performs a one-time migration for older comment formats.
        """
        chat_cache = get_chat_cache()
        comments = chat_cache.get(COMMENTS_KEY) or []
        
        # One-time migration for old comment formats
        needs_update = False
        for c in comments:
            updated = False
            if 'id' not in c:
                c['id'] = str(uuid.uuid4())
                updated = True
            if 'ip_prefix' not in c and 'ip' in c:
                c['ip_prefix'] = get_ip_prefix(c['ip'])
                c.pop('ip', None)
                updated = True
            elif 'ip' in c:
                c.pop('ip', None)
                updated = True
            
            if updated:
                needs_update = True

        if needs_update:
            chat_cache.put(COMMENTS_KEY, comments)

        return comments, 200

    @limiter.limit(dynamic_rate_limit)
    def post(self):
        """
        Handles new comment submissions. Validates input, sanitizes content,
        and adds the new comment to the cache.
        """
        ip = request.remote_addr
        chat_cache = get_chat_cache()
        banned_ips = chat_cache.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return {"error": "Your IP address has been banned from commenting."}, 403

        data = request.get_json()
        text = data.get('text', '').strip()
        image_url = data.get('image_url', '').strip()

        if not text and not image_url:
            return {"error": "Comment cannot be empty."}, 400

        # Sanitize HTML, allowing only <b> tags
        sanitized_text = html.escape(text).replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')

        # Validate image URL
        valid_image_url = None
        if image_url:
            is_local_upload = image_url.startswith(WEB_UPLOAD_PATH + '/')
            is_external_url = image_url.startswith('http://') or image_url.startswith('https://')
            is_data_url = image_url.startswith('data:image/')

            if is_local_upload or is_external_url or is_data_url:
                if not is_data_url:
                    has_valid_extension = image_url.lower().endswith(tuple(f".{ext}" for ext in ALLOWED_EXTENSIONS))
                    if has_valid_extension:
                        valid_image_url = image_url
                else:
                    valid_image_url = image_url
        
        comment = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "ip_prefix": get_ip_prefix(ip),
            "text": sanitized_text,
            "image_url": valid_image_url
        }

        comments = chat_cache.get(COMMENTS_KEY) or []
        comments.append(comment)
        comments = comments[-MAX_COMMENTS:]
        chat_cache.put(COMMENTS_KEY, comments)

        return {"success": True}, 201


class CommentStreamResource(Resource):
    """
    Resource for handling GET requests to /api/comments/stream.
    """
    
    def get(self):
        """
        Provides a real-time stream of comments using Server-Sent Events (SSE).
        Pushes updates to clients whenever the comment list changes.
        """
        def event_stream():
            last_data_sent = None
            chat_cache = get_chat_cache()
            while True:
                try:
                    current_comments = chat_cache.get(COMMENTS_KEY) or []
                    current_data = json.dumps(current_comments)
                    if current_data != last_data_sent:
                        yield f"event: new_comment\ndata: {current_data}\n\n"
                        last_data_sent = current_data
                    time.sleep(2)
                except GeneratorExit:
                    break
                except Exception as e:
                    print(f"SSE Error in chat stream: {e}")
                    break
        return Response(event_stream(), mimetype='text/event-stream')


class CommentResource(Resource):
    """
    Resource for handling DELETE requests to /api/comments/<comment_id>.
    """
    
    @login_required
    def delete(self, comment_id):
        """
        Deletes a specific comment by its ID. Requires admin login.
        """
        chat_cache = get_chat_cache()
        comments = chat_cache.get(COMMENTS_KEY) or []
        
        comments_after_delete = [c for c in comments if c.get('id') != comment_id]

        if len(comments_after_delete) < len(comments):
            chat_cache.put(COMMENTS_KEY, comments_after_delete)
            return {"success": True}, 200
        else:
            return {"error": "Comment not found"}, 404


class ImageUploadResource(Resource):
    """
    Resource for handling POST requests to /api/upload_image.
    """
    
    @limiter.limit(dynamic_rate_limit)
    def post(self):
        """
        Handles image uploads for chat comments. Validates file type and size,
        saves the file, and returns a web-accessible URL.
        """
        ip = request.remote_addr
        chat_cache = get_chat_cache()
        banned_ips = chat_cache.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return {"error": "Your IP address has been banned from uploading."}, 403

        if 'image' not in request.files:
            return {"error": "No image file part in the request."}, 400

        file = request.files['image']
        if file.filename == '':
            return {"error": "No file selected for upload."}, 400

        if not file or not allowed_file(file.filename):
            return {"error": "Invalid file type. Allowed types: " + ", ".join(ALLOWED_EXTENSIONS)}, 400

        # Check file size
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        if file_length > MAX_IMAGE_SIZE:
            return {"error": f"File size exceeds the limit of {MAX_IMAGE_SIZE // 1024 // 1024} MB."}, 400
        file.seek(0)

        # Save file with a secure, unique name
        _, ext = os.path.splitext(file.filename)
        filename = secure_filename(f"{uuid.uuid4()}{ext}")
        
        # Ensure the upload directory exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        try:
            file.save(filepath)
            file_url = f"{WEB_UPLOAD_PATH}/{filename}"
            return {"success": True, "url": file_url}, 201
        except (IOError, OSError) as e:
            print(f"Error saving uploaded image: {e}")
            return {"error": "Failed to save the uploaded image on the server."}, 500


def init_chat_routes(app, limiter, dynamic_rate_limit):
    """
    Initializes all chat-related routes for the Flask application using Flask-RESTful.

    Args:
        app (Flask): The Flask application instance.
        limiter (Flask-Limiter): The rate limiter instance.
        dynamic_rate_limit (function): Function to determine rate limit string.
    """
    # Register Flask-RESTful resources
    API.add_resource(CommentsResource, '/api/comments')
    API.add_resource(CommentStreamResource, '/api/comments/stream')
    API.add_resource(CommentResource, '/api/comments/<comment_id>')
    API.add_resource(ImageUploadResource, '/api/upload_image')

