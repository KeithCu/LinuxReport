import os
import json
import datetime
from flask import render_template, request, jsonify
from flask_login import current_user, login_required
from shared import MODE_MAP, MODE, PATH, FAVICON, LOGO_URL, WEB_DESCRIPTION

def init_old_headlines_routes(app):
    @app.route('/old_headlines')
    def old_headlines():
        mode_str = MODE_MAP.get(MODE)
        archive_file = os.path.join(PATH, f"{mode_str}report_archive.jsonl")
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
            print(f"Error reading archive file {archive_file}: {e}")

        # Sort headlines by timestamp
        headlines.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Skip the first 3 headlines (most recent)
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
        grouped_headlines_list = [(date, headlines) for date, headlines in grouped_headlines.items()]
        grouped_headlines_list.sort(key=lambda x: datetime.datetime.strptime(x[0], '%B %d, %Y'), reverse=True)

        # Use Flask-Login for admin authentication
        is_admin = current_user.is_authenticated
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

    @app.route('/api/delete_headline', methods=['POST'])
    @login_required
    def delete_headline():
        data = request.get_json()
        url = data.get('url')
        timestamp = data.get('timestamp')
        mode_str = MODE_MAP.get(MODE)
        archive_file = os.path.join(PATH, f"{mode_str}report_archive.jsonl")
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
                except Exception:
                    pass
                new_lines.append(line)
            if deleted:
                with open(archive_file, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
