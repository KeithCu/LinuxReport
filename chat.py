import os
import json
import uuid
import html
import datetime
import time
from flask import jsonify, Response, request
from flask_login import login_required
from werkzeug.utils import secure_filename
from shared import (get_chat_cache, get_ip_prefix, PATH)

# Chat Constants
MAX_COMMENTS = 1000
COMMENTS_KEY = "chat_comments"
BANNED_IPS_KEY = "banned_ips"
WEB_UPLOAD_PATH = '/static/uploads' # Define the web-accessible path prefix
UPLOAD_FOLDER = PATH + WEB_UPLOAD_PATH # Define absolute upload folder for server deployment
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'} # Allowed image types
MAX_IMAGE_SIZE = 5 * 1024 * 1024 # 5 MB

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_chat_routes(app, limiter, dynamic_rate_limit):
    @app.route('/api/comments', methods=['GET'])
    def get_comments():
        chat_cache = get_chat_cache()
        comments = chat_cache.get(COMMENTS_KEY) or []
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

        return jsonify(comments)

    @app.route('/api/comments/stream')
    def stream_comments():
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
                    print(f"SSE Error: {e}")
                    break
        return Response(event_stream(), mimetype='text/event-stream')

    @app.route('/api/comments', methods=['POST'])
    @limiter.limit(dynamic_rate_limit)
    def post_comment():
        ip = request.remote_addr
        chat_cache = get_chat_cache()
        banned_ips = chat_cache.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return jsonify({"error": "Banned"}), 403

        data = request.get_json()
        text = data.get('text', '').strip()
        image_url = data.get('image_url', '').strip()

        if not text and not image_url:
            return jsonify({"error": "Comment cannot be empty"}), 400

        sanitized_text = html.escape(text).replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')

        valid_image_url = None
        if image_url:
            is_local_upload = image_url.startswith(WEB_UPLOAD_PATH + '/')
            is_external_url = image_url.startswith('http://') or image_url.startswith('https://')
            is_data_url = image_url.startswith('data:image/')

            if is_local_upload or is_external_url or is_data_url:
                if not is_data_url:
                    has_valid_extension = image_url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
                    if has_valid_extension:
                        valid_image_url = image_url
                else:
                    valid_image_url = image_url

        comment_id = str(uuid.uuid4())
        ip_prefix = get_ip_prefix(ip)

        comment = {
            "id": comment_id,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "ip_prefix": ip_prefix,
            "text": sanitized_text,
            "image_url": valid_image_url
        }

        comments = chat_cache.get(COMMENTS_KEY) or []
        comments.append(comment)
        comments = comments[-MAX_COMMENTS:]
        chat_cache.put(COMMENTS_KEY, comments)

        return jsonify({"success": True}), 201

    @app.route('/api/comments/<comment_id>', methods=['DELETE'])
    @login_required
    def delete_comment(comment_id):
        chat_cache = get_chat_cache()
        comments = chat_cache.get(COMMENTS_KEY) or []
        initial_length = len(comments)

        comments_after_delete = [c for c in comments if c.get('id') != comment_id]
        final_length = len(comments_after_delete)

        if final_length < initial_length:
            try:
                chat_cache.put(COMMENTS_KEY, comments_after_delete)
                return jsonify({"success": True}), 200
            except Exception as e:
                return jsonify({"error": "Failed to update cache after deletion"}), 500
        else:
            return jsonify({"error": "Comment not found"}), 404

    @app.route('/api/upload_image', methods=['POST'])
    @limiter.limit(dynamic_rate_limit)
    def upload_image():
        ip = request.remote_addr
        chat_cache = get_chat_cache()
        banned_ips = chat_cache.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return jsonify({"error": "Banned"}), 403

        if 'image' not in request.files:
            return jsonify({"error": "No image file part"}), 400

        file = request.files['image']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file and allowed_file(file.filename):
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            if file_length > MAX_IMAGE_SIZE:
                return jsonify({"error": "File size exceeds limit"}), 400
            file.seek(0)

            _, ext = os.path.splitext(file.filename)
            filename = secure_filename(f"{uuid.uuid4()}{ext}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            try:
                file.save(filepath)
                file_url = f"{WEB_UPLOAD_PATH}/{filename}"
                return jsonify({"success": True, "url": file_url}), 201
            except (IOError, OSError) as e:
                return jsonify({"error": "Failed to save image"}), 500
        else:
            return jsonify({"error": "Invalid file type"}), 400
