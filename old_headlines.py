import os
import json
import datetime
from pathlib import Path
from flask import render_template, request, jsonify
from flask_login import current_user, login_required
from flask_restful import Resource
from shared import MODE_MAP, MODE, PATH, FAVICON, LOGO_URL, WEB_DESCRIPTION, API, g_logger, g_c
from caching import get_cached_page


class DeleteHeadlineResource(Resource):
    """
    Resource for handling DELETE requests to delete headlines from the archive.
    """
    
    @login_required
    def post(self):
        """
        Deletes a headline from the archive file based on URL and timestamp.
        """
        data = request.get_json()
        url = data.get('url')
        timestamp = data.get('timestamp')
        mode_str = MODE_MAP.get(MODE)
        archive_file = Path(PATH) / f"{mode_str}report_archive.jsonl"
        
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            deleted = False
            for line in lines:
                try:
                    entry = json.loads(line)
                    if entry.get('url') == url and entry.get('timestamp') == timestamp:
                        deleted = True
                        continue
                except json.JSONDecodeError:
                    pass
                new_lines.append(line)
            if deleted:
                with open(archive_file, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                return {'success': True}, 200
            else:
                return {'error': 'Not found'}, 404
        except (IOError, OSError) as e:
            return {'error': str(e)}, 500


def init_old_headlines_routes(app):
    """
    Initialize old headlines routes for the Flask application.
    
    Args:
        app (Flask): Flask application instance
    """
    # Register the page route (kept as traditional Flask route)
    @app.route('/old_headlines')
    def old_headlines():
        mode_str = MODE_MAP.get(MODE)
        archive_file = Path(PATH) / f"{mode_str}report_archive.jsonl"
        is_admin = current_user.is_authenticated

        def render_old_headlines_page():
            headlines = []
            try:
                with open(archive_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            # Convert timestamp to datetime object for grouping
                            if 'timestamp' in entry:
                                entry['date'] = datetime.datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00')).date()
                            headlines.append(entry)
                        except json.JSONDecodeError:
                            continue
            except FileNotFoundError:
                pass
            except IOError as e:
                g_logger.warning(f"Error reading archive file {archive_file}: {e}")

            # Sort headlines by timestamp
            headlines.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Skip the first 3 headlines (most recent) - these are on the main page
            if len(headlines) > 3:
                headlines = headlines[3:]
            else:
                headlines = []

            # Group headlines by date
            grouped_headlines = {}
            for headline in headlines:
                date = headline.get('date')
                if date:
                    date_str = date.strftime('%B %d, %Y')  # Format: January 1, 2024
                    if date_str not in grouped_headlines:
                        grouped_headlines[date_str] = []
                    grouped_headlines[date_str].append(headline)

            # Convert to list of tuples (date, headlines) and sort by date
            grouped_headlines_list = []
            for date_str, heads in grouped_headlines.items():
                # Group headlines by exact timestamp within this date and fetch LLM attempts for all users
                time_groups = {}
                for h in heads:
                    ts = h.get('timestamp')
                    if ts not in time_groups:
                        time_groups[ts] = {
                            'headlines': [],
                            'attempts': g_c.get(f"llm_attempts:{mode_str}:{ts}")
                        }
                    time_groups[ts]['headlines'].append(h)
                
                # Sort time groups by timestamp descending
                sorted_times = sorted(time_groups.items(), key=lambda x: x[0], reverse=True)
                grouped_headlines_list.append((date_str, sorted_times))

            grouped_headlines_list.sort(key=lambda x: datetime.datetime.strptime(x[0], '%B %d, %Y'), reverse=True)

            return render_template(
                'old_headlines.html',
                grouped_headlines=grouped_headlines_list,
                mode=mode_str,
                title=f"Old Headlines - {mode_str.title()}Report",
                favicon=FAVICON,
                logo_url=LOGO_URL,
                description=WEB_DESCRIPTION,
                is_admin=is_admin
            )

        # Cache key includes admin status because we show extra info for admins
        cache_key = f'old_headlines:{mode_str}:{"admin" if is_admin else "user"}'
        return get_cached_page(cache_key, render_old_headlines_page, archive_file)
    
    # Register Flask-RESTful resource
    API.add_resource(DeleteHeadlineResource, '/api/delete_headline')
