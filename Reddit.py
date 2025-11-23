"""
Reddit.py

Handles PRAW (Python Reddit API Wrapper) authentication and fetching Reddit feeds in a feedparser-compatible format for the LinuxReport project.

USAGE & CONFIG SUMMARY (READ THIS FIRST):

- Do NOT put Reddit client_id, client_secret, username, or password into config.yaml or any tracked file.
- Do NOT commit reddit_token.json to git.

Bootstrap (one-time, interactive, on the server):

1. On the deployment server, from the LinuxReport project directory, run this module directly:
   python Reddit.py

2. When prompted, enter:
   - Reddit Client ID
   - Reddit Client Secret
   - Reddit Username
   - Reddit Password (stored securely for PRAW authentication)

3. This script will:
   - Store the credentials in "reddit_token.json" for PRAW to use.
   - Set permissions on reddit_token.json to 0600 (owner read/write only).
   - PRAW handles token refresh automatically.

Runtime behavior:

- At runtime, get_valid_reddit_client() creates a PRAW Reddit instance from reddit_token.json.
- workers.py uses fetch_reddit_feed_as_feedparser() (when ENABLE_REDDIT_API_FETCH is True)
  to fetch Reddit data via PRAW using the stored credentials.
- No secrets are loaded from config.yaml by default.
- PRAW automatically handles authentication and token refresh.
"""

import getpass
import json
# Standard library imports
import os
import re
import time
from urllib.parse import urlparse

# Third-party imports
import praw

# Local imports
from shared import g_logger

# --- Configuration ---
# Credentials are handled via the token file for PRAW authentication

CREDENTIALS_FILE = 'reddit_token.json' # Simple file storage for PRAW credentials

# --- User Agent Domain Extraction ---
URL_IMAGES = None  # Should be set from config (or default)

def extract_domain_from_url_images(url_images):
    if not url_images:
        return "linuxreport.net"
    url = url_images
    if url.startswith('https://'):
        url = url[len('https://'):]
    elif url.startswith('http://'):
        url = url[len('http://'):]
    if url.endswith('/static/images'):
        url = url[:-len('/static/images')]
    url = url.rstrip('/')
    return url

# USER_AGENT is constructed by PRAW using the username from credentials

# --- Token Handling ---

def save_token(credentials):
    """Saves PRAW credentials (client_id, client_secret, username, password) to a file."""
    try:
        # Ensure sensitive data like client_secret isn't inadvertently logged
        # In a real app, consider encrypting CREDENTIALS_FILE or using secure storage
        g_logger.info(f"Saving credentials for user '{credentials.get('username', 'N/A')}' to {CREDENTIALS_FILE}")
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(credentials, f, indent=4) # Add indent for readability
        os.chmod(CREDENTIALS_FILE, 0o600) # Read/write only for owner
    except (IOError, OSError, TypeError) as e:
        g_logger.error(f"Error saving credentials file '{CREDENTIALS_FILE}': {e}")


def load_token():
    """Loads PRAW credentials (client_id, client_secret, username, password) from a file."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            credentials = json.load(f)
            # Basic validation: check for essential PRAW keys
            if not all(k in credentials for k in ['client_id', 'client_secret', 'username', 'password']):
                 g_logger.warning(f"Token file '{CREDENTIALS_FILE}' is missing essential PRAW credentials. Re-authentication may be required.")
                 return None
            return credentials
    except (IOError, json.JSONDecodeError, OSError, TypeError) as e:
        g_logger.error(f"Error loading or parsing credentials file '{CREDENTIALS_FILE}': {e}")
        return None

def get_valid_reddit_client():
    """
    Gets a valid PRAW Reddit client instance,
    prompting for initial credentials if needed.
    PRAW handles token refresh automatically.
    Returns:
        praw.Reddit instance or None on failure.
    """
    token_data = load_token()

    # Check if we need to migrate from old token format or get new credentials
    if not token_data or not all(k in token_data for k in ['client_id', 'client_secret', 'username', 'password']):
        if token_data:
            g_logger.info("Existing token file found but needs migration to PRAW format.")
        else:
            g_logger.info(f"No token file found ('{CREDENTIALS_FILE}') or file is invalid.")

        g_logger.info("Please provide your Reddit API credentials for initial setup.")
        try:
            client_id = input("Enter your Reddit Client ID: ").strip()
            client_secret = getpass.getpass("Enter your Reddit Client Secret: ").strip()
            username = input("Enter your Reddit Username: ").strip()
            password = getpass.getpass("Enter your Reddit Password (stored securely for PRAW): ").strip()

            if not all([client_id, client_secret, username, password]):
                g_logger.error("Error: All credentials must be provided for initial setup.")
                return None

            # Store credentials in new format for PRAW
            credentials = {
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password,
                'user_agent': f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{username})'
            }
            save_token(credentials)
            g_logger.info("Credentials saved successfully.")
        except EOFError: # Handle running in non-interactive environment
             g_logger.error("\nError: Cannot prompt for credentials in non-interactive mode and no token file found.")
             return None
        except (IOError, OSError, ValueError) as e: # Catch other potential input errors
             g_logger.error(f"\nAn error occurred during credential input: {e}")
             return None
    else:
        # Load existing PRAW-compatible credentials
        credentials = token_data

    # Create PRAW Reddit instance
    try:
        reddit = praw.Reddit(
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret'],
            username=credentials['username'],
            password=credentials['password'],
            user_agent=credentials.get('user_agent', f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{credentials["username"]})')
        )
        # Test the connection by trying to access user info
        reddit.user.me()
        g_logger.info(f"Successfully authenticated as user: {credentials['username']}")
        return reddit
    except Exception as e:
        g_logger.error(f"Failed to create PRAW Reddit client: {e}")
        return None

def parse_reddit_url(url):
    """
    Parses a Reddit URL to extract subreddit and feed type.

    Handles URLs like:
    - https://www.reddit.com/r/linux/hot/.rss
    - https://www.reddit.com/r/archlinux/new
    - https://reddit.com/r/AskElectronics/

    Returns:
        tuple: (subreddit, feed_type) or (None, None) if invalid.
               Feed type defaults to 'hot'.
    """
    try:
        parsed_url = urlparse(url)
        # Robustly split path, removing empty segments from leading/trailing slashes
        path_parts = [part for part in parsed_url.path.split('/') if part]

        if not path_parts or path_parts[0].lower() != 'r' or len(path_parts) < 2:
            return None, None # Must start with /r/ and have a subreddit name

        subreddit = path_parts[1]
        # Basic check for valid subreddit characters
        if not re.match(r'^[a-zA-Z0-9_]+$', subreddit):
            g_logger.warning(f"Invalid subreddit format found: {subreddit}")
            return None, None

        feed_type = 'hot' # Default
        possible_feeds = ['hot', 'new', 'rising', 'controversial', 'top']

        if len(path_parts) > 2:
            # Check third part, removing potential .rss/.json suffix
            potential_feed = path_parts[2].lower().rsplit('.', 1)[0]
            if potential_feed in possible_feeds:
                feed_type = potential_feed

        return subreddit, feed_type
    except (AttributeError, TypeError, ValueError) as e:
        g_logger.error(f"Error parsing URL '{url}': {e}")
        return None, None


def format_reddit_entry(submission):
    """Formats a single PRAW Submission object into a feedparser-like entry dict."""
    try:
        entry = {}
        entry['title'] = submission.title or ''
        entry['author'] = submission.author.name if submission.author else ''
        # Reddit 'permalink' is relative, needs domain prepended
        entry['link'] = f"https://www.reddit.com{submission.permalink}" if submission.permalink else ''
        # Use Reddit's 'name' (e.g., t3_xxxxx) as the stable ID
        entry['id'] = submission.name or entry['link'] # Fallback to link if name missing

        # Summary & Content (Mimic feedparser structure)
        summary = submission.selftext or '' # Markdown version
        content_html = submission.selftext_html # HTML version

        # If not a self-post and summary is empty, use the external URL as summary
        if not submission.is_self and not summary:
            summary = submission.url or '' # Link posts point to external URL here
        entry['summary'] = summary

        # feedparser 'content' is often a list of dicts
        entry['content'] = []
        if content_html:
             # Note: Reddit's selftext_html from PRAW may already be unescaped
            entry['content'].append({
                 'type': 'text/html',
                 'language': None,
                 'base': entry['link'],
                 'value': content_html
             })
        elif summary and submission.is_self: # Only add plain text content for self posts
            entry['content'].append({
                 'type': 'text/plain',
                 'language': None,
                 'base': entry['link'],
                 'value': summary
            })

        # Time parsing - Reddit provides UTC timestamp
        created_utc = submission.created_utc
        if created_utc:
            try:
                # feedparser uses time.struct_time in UTC/GMT for _parsed fields
                published_parsed = time.gmtime(float(created_utc))
                entry['published_parsed'] = published_parsed
                # Standard RSS/Atom time format string
                entry['published'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT', published_parsed)
                # Use published time for updated time as well, as Reddit doesn't track updates in listings
                entry['updated_parsed'] = published_parsed
                entry['updated'] = entry['published']
            except (ValueError, TypeError):
                g_logger.warning(f"Could not parse timestamp {created_utc}")
                entry['published_parsed'] = None
                entry['published'] = None
                entry['updated_parsed'] = None
                entry['updated'] = None

        # Add custom Reddit-specific fields, prefixed for clarity
        entry['reddit_score'] = submission.score
        entry['reddit_num_comments'] = submission.num_comments
        # Provide thumbnail URL only if it's a valid image URL
        thumb = submission.thumbnail
        entry['reddit_thumbnail'] = thumb if thumb and isinstance(thumb, str) and thumb.startswith('http') else None
        entry['reddit_url'] = submission.url # The external link for link posts
        entry['reddit_domain'] = submission.domain
        entry['reddit_is_self'] = submission.is_self
        entry['reddit_subreddit'] = submission.subreddit.display_name if submission.subreddit else ''

        return entry
    except Exception as e:
        g_logger.error(f"Error formatting PRAW submission: {e}")
        return None


def fetch_reddit_feed_as_feedparser(feed_url):
    """
    Fetches data from Reddit API based on an RSS-like URL
    and returns it in a structure similar to feedparser output.
    Uses PRAW for authentication and API calls.
    """
    subreddit, feed_type = parse_reddit_url(feed_url)

    if not subreddit or not feed_type:
        g_logger.error(f"Could not parse subreddit/feed type from URL: {feed_url}")
        # Return a structure indicating failure, similar to feedparser's bozo=1
        return {
            'bozo': 1,
            'bozo_exception': ValueError(f"Invalid Reddit URL format: {feed_url}"),
            'feed': {},
            'entries': [],
            'status': 400, # Indicate bad request
            'href': feed_url
        }

    # Get PRAW Reddit client
    reddit = get_valid_reddit_client()
    if not reddit:
        g_logger.error("Could not obtain valid PRAW Reddit client.")
        # Return structure indicating auth failure
        return {
            'bozo': 1,
            'bozo_exception': ConnectionError("Failed to get PRAW Reddit client"),
            'feed': {},
            'entries': [],
            'status': 401, # Indicate auth failure
            'href': feed_url
        }

    # Construct PRAW subreddit and feed URL for logging
    praw_url = f"https://www.reddit.com/r/{subreddit}/{feed_type}"

    g_logger.info(f"Fetching {feed_type} feed for r/{subreddit} using PRAW")
    output = {
        'bozo': 0, # Assume success unless errors occur
        'bozo_exception': None,
        'feed': {},
        'entries': [],
        'headers': {},
        'href': praw_url,
        'status': 200, # PRAW doesn't use HTTP status codes
        'encoding': 'utf-8',
        'version': 'praw_api_v1' # Custom version identifier
    }

    try:
        # Get the subreddit object
        subreddit_obj = reddit.subreddit(subreddit)

        # Get submissions based on feed type
        if feed_type == 'hot':
            submissions = subreddit_obj.hot(limit=25)
        elif feed_type == 'new':
            submissions = subreddit_obj.new(limit=25)
        elif feed_type == 'rising':
            submissions = subreddit_obj.rising(limit=25)
        elif feed_type == 'controversial':
            submissions = subreddit_obj.controversial(limit=25)
        elif feed_type == 'top':
            submissions = subreddit_obj.top(limit=25)
        else:
            # Default to hot if unknown feed type
            submissions = subreddit_obj.hot(limit=25)

        # Convert generator to list to get the first item for feed metadata
        submissions_list = list(submissions)

    except Exception as e:
        msg = f"Error fetching Reddit data with PRAW: {e}"
        g_logger.error(f"Error: {msg}")
        output['bozo'] = 1
        output['bozo_exception'] = e
        # Attempt to populate feed info even on error
        output['feed']['title'] = f"r/{subreddit} - {feed_type} (Error)"
        output['feed']['link'] = praw_url
        return output

    # --- Format the successful output ---

    # Populate feed metadata
    output['feed']['title'] = f"r/{subreddit} - {feed_type}"
    # Link to the human-viewable Reddit page for the feed
    output['feed']['link'] = praw_url
    output['feed']['links'] = [{'rel': 'alternate', 'type': 'text/html', 'href': output['feed']['link']}]
    output['feed']['subtitle'] = f"Posts from r/{subreddit} sorted by {feed_type} via PRAW"
    output['feed']['language'] = 'en' # Assume English

    # Use the timestamp of the newest post as the feed's updated time
    if submissions_list:
        first_submission = submissions_list[0]
        created_utc = first_submission.created_utc
        if created_utc:
            try:
                updated_parsed = time.gmtime(float(created_utc))
                output['feed']['updated_parsed'] = updated_parsed
                output['feed']['updated'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT', updated_parsed)
            except (ValueError, TypeError):
                pass # Ignore if timestamp is bad

    # Populate entries
    for submission in submissions_list:
        entry = format_reddit_entry(submission)
        if entry:
            output['entries'].append(entry)

    if not submissions_list:
        g_logger.info(f"Note: No posts found for r/{subreddit}/{feed_type} (Subreddit might be empty or filtered).")
        # Still a valid response, just no entries. bozo remains 0.

    return output

# --- Main Execution Logic ---
if __name__ == '__main__':
    g_logger.info("Attempting to ensure a valid PRAW Reddit client can be created...")
    # This call will handle loading, prompting for initial creds
    reddit = get_valid_reddit_client()

    if reddit:
        g_logger.info(f"\nSuccessfully created PRAW Reddit client for user: {reddit.user.me().name}.")
        g_logger.info("You can now use functions like fetch_reddit_feed_as_feedparser.")

        # Example usage (optional):
        # test_url = "https://www.reddit.com/r/python/hot/.rss"
        # print(f"\nAttempting to fetch example feed: {test_url}")
        # feed_data = fetch_reddit_feed_as_feedparser(test_url)
        # if feed_data and not feed_data.get('bozo'):
        #     print(f"Successfully fetched {len(feed_data.get('entries', []))} entries.")
        #     # print(json.dumps(feed_data, indent=2)) # Pretty print result
        # elif feed_data:
        #     print(f"Failed to fetch feed. Status: {feed_data.get('status')}, Error: {feed_data.get('bozo_exception')}")
        # else:
        #     print("Failed to fetch feed (returned None).")

    else:
        g_logger.error("\nFailed to create a valid PRAW Reddit client. Cannot proceed with API calls.")
        g_logger.error(f"Check for errors above. If it's the first run, ensure you provide correct credentials when prompted.")
        g_logger.error(f"Make sure the token file '{CREDENTIALS_FILE}' is writable if it needs to be created/updated.")
