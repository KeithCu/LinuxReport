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
from shared import g_logger, URL_IMAGES

# --- Configuration ---
# Credentials are handled via the token file for PRAW authentication

CREDENTIALS_FILE = 'reddit_token.json' # Simple file storage for PRAW credentials
DEFAULT_FEED_LIMIT = 25
FEED_TYPES = ['hot', 'new', 'rising', 'controversial', 'top']
REQUIRED_CREDENTIAL_KEYS = ['client_id', 'client_secret', 'username', 'password']

def extract_domain_from_url_images(url_images):
    """Extracts domain from URL_IMAGES config value for user agent construction."""
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


def _create_error_response(status, exception, feed_url, title_suffix=''):
    """
    Creates a standardized error response structure compatible with feedparser format.
    
    Args:
        status: HTTP status code
        exception: Exception object or error message
        feed_url: Original feed URL
        title_suffix: Optional suffix for feed title
        
    Returns:
        dict: Standardized error response structure
    """
    return {
        'bozo': 1,
        'bozo_exception': exception,
        'feed': {'title': f"Reddit Feed{title_suffix}", 'link': feed_url} if title_suffix else {},
        'entries': [],
        'status': status,
        'href': feed_url
    }


def _parse_timestamp(created_utc):
    """
    Parses Reddit UTC timestamp into feedparser-compatible format.
    
    Args:
        created_utc: Unix timestamp (float or int)
        
    Returns:
        tuple: (published_parsed, published_str) or (None, None) on error
    """
    if not created_utc:
        return None, None
    try:
        published_parsed = time.gmtime(float(created_utc))
        published_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', published_parsed)
        return published_parsed, published_str
    except (ValueError, TypeError):
        return None, None


def _get_submissions(subreddit_obj, feed_type, limit=DEFAULT_FEED_LIMIT):
    """
    Fetches submissions from a subreddit based on feed type.
    
    Args:
        subreddit_obj: PRAW Subreddit object
        feed_type: Type of feed ('hot', 'new', 'rising', 'controversial', 'top')
        limit: Maximum number of submissions to fetch
        
    Returns:
        Generator: PRAW submission generator
    """
    feed_methods = {
        'hot': subreddit_obj.hot,
        'new': subreddit_obj.new,
        'rising': subreddit_obj.rising,
        'controversial': subreddit_obj.controversial,
        'top': subreddit_obj.top
    }
    method = feed_methods.get(feed_type, subreddit_obj.hot)
    return method(limit=limit)

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
            # Validate: check for essential PRAW keys
            if not all(k in credentials for k in REQUIRED_CREDENTIAL_KEYS):
                 g_logger.debug(f"Credentials file '{CREDENTIALS_FILE}' exists but is missing required PRAW credentials. Will prompt for new credentials.")
                 return None
            return credentials
    except json.JSONDecodeError as e:
        g_logger.error(f"Error parsing JSON from credentials file '{CREDENTIALS_FILE}': {e}. File may be corrupted or invalid.")
        return None
    except (IOError, OSError) as e:
        g_logger.error(f"Error reading credentials file '{CREDENTIALS_FILE}': {e}")
        return None
    except TypeError as e:
        g_logger.error(f"Unexpected data type in credentials file '{CREDENTIALS_FILE}': {e}")
        return None

def get_valid_reddit_client():
    """
    Gets a valid PRAW Reddit client instance,
    prompting for initial credentials if needed.
    PRAW handles token refresh automatically.
    Returns:
        praw.Reddit instance or None on failure.
    """
    credentials = load_token()

    if not credentials:
        g_logger.info(f"No valid credentials file found ('{CREDENTIALS_FILE}'). Prompting for Reddit API credentials.")
        try:
            client_id = input("Enter your Reddit Client ID: ").strip()
            client_secret = getpass.getpass("Enter your Reddit Client Secret: ").strip()
            username = input("Enter your Reddit Username: ").strip()
            password = getpass.getpass("Enter your Reddit Password (stored securely for PRAW): ").strip()

            if not all([client_id, client_secret, username, password]):
                g_logger.error("Error: All credentials must be provided for initial setup. Missing one or more required fields.")
                return None

            # Store credentials for PRAW
            credentials = {
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password,
                'user_agent': f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{username})'
            }
            save_token(credentials)
            g_logger.info(f"Credentials saved successfully to '{CREDENTIALS_FILE}' for user '{username}'.")
        except EOFError:
             g_logger.error("Error: Cannot prompt for credentials in non-interactive mode. Please create credentials file manually or run in interactive mode.")
             return None
        except (IOError, OSError) as e:
             g_logger.error(f"Error reading input or saving credentials: {e}")
             return None
        except ValueError as e:
             g_logger.error(f"Invalid input value: {e}")
             return None

    # Create PRAW Reddit instance
    try:
        g_logger.debug(f"Creating PRAW Reddit client for user '{credentials['username']}'")
        reddit = praw.Reddit(
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret'],
            username=credentials['username'],
            password=credentials['password'],
            user_agent=credentials.get('user_agent', f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{credentials["username"]})')
        )
        # Test the connection by trying to access user info
        try:
            user = reddit.user.me()
            g_logger.info(f"Successfully authenticated as user: {user.name}")
        except praw.exceptions.Forbidden as e:
            g_logger.error(f"Authentication failed: Reddit API returned Forbidden (403). User '{credentials['username']}' may be suspended or credentials may be invalid: {e}")
            return None
        except praw.exceptions.Unauthorized as e:
            g_logger.error(f"Authentication failed: Reddit API returned Unauthorized (401). Invalid credentials for user '{credentials['username']}': {e}")
            return None
        except Exception as e:
            g_logger.error(f"Authentication test failed for user '{credentials['username']}': {e}")
            return None
        return reddit
    except KeyError as e:
        g_logger.error(f"Missing required credential field: {e}. Credentials file may be corrupted.")
        return None
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

        feed_type = 'hot'  # Default

        if len(path_parts) > 2:
            # Check third part, removing potential .rss/.json suffix
            potential_feed = path_parts[2].lower().rsplit('.', 1)[0]
            if potential_feed in FEED_TYPES:
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
        published_parsed, published_str = _parse_timestamp(submission.created_utc)
        if published_parsed:
            entry['published_parsed'] = published_parsed
            entry['published'] = published_str
            # Use published time for updated time as well, as Reddit doesn't track updates in listings
            entry['updated_parsed'] = published_parsed
            entry['updated'] = published_str
        else:
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
    except AttributeError as e:
        g_logger.error(f"Error formatting PRAW submission: Missing expected attribute. Submission may be deleted or malformed: {e}")
        return None
    except Exception as e:
        g_logger.error(f"Error formatting PRAW submission: Unexpected error: {e}")
        return None


def _create_success_response(praw_url):
    """Creates base structure for successful feed response."""
    return {
        'bozo': 0,
        'bozo_exception': None,
        'feed': {},
        'entries': [],
        'headers': {},
        'href': praw_url,
        'status': 200,
        'encoding': 'utf-8',
        'version': 'praw_api_v1'
    }


def _populate_feed_metadata(output, subreddit, feed_type, praw_url, submissions_list):
    """Populates feed metadata in the output structure."""
    output['feed']['title'] = f"r/{subreddit} - {feed_type}"
    output['feed']['link'] = praw_url
    output['feed']['links'] = [{'rel': 'alternate', 'type': 'text/html', 'href': praw_url}]
    output['feed']['subtitle'] = f"Posts from r/{subreddit} sorted by {feed_type} via PRAW"
    output['feed']['language'] = 'en'
    
    # Use the timestamp of the newest post as the feed's updated time
    if submissions_list:
        updated_parsed, updated_str = _parse_timestamp(submissions_list[0].created_utc)
        if updated_parsed:
            output['feed']['updated_parsed'] = updated_parsed
            output['feed']['updated'] = updated_str


def _handle_praw_exception(e, subreddit, feed_type, praw_url, output):
    """
    Handles PRAW exceptions and updates output accordingly.
    
    Returns:
        bool: True if exception was handled, False otherwise
    """
    exception_handlers = {
        praw.exceptions.NotFound: (404, f"r/{subreddit} - {feed_type} (Not Found)", 
                                   f"Subreddit 'r/{subreddit}' not found or does not exist"),
        praw.exceptions.Forbidden: (403, f"r/{subreddit} - {feed_type} (Forbidden)",
                                   f"Access forbidden to subreddit 'r/{subreddit}'. Subreddit may be private or banned."),
        praw.exceptions.RedditAPIException: (500, f"r/{subreddit} - {feed_type} (API Error)",
                                            f"Reddit API error fetching 'r/{subreddit}/{feed_type}'")
    }
    
    for exc_type, (status, title, log_msg) in exception_handlers.items():
        if isinstance(e, exc_type):
            g_logger.error(f"{log_msg}: {e}")
            output['bozo'] = 1
            output['bozo_exception'] = e
            output['feed']['title'] = title
            output['feed']['link'] = praw_url
            output['status'] = status
            return True
    return False


def fetch_reddit_feed_as_feedparser(feed_url):
    """
    Fetches data from Reddit API based on an RSS-like URL
    and returns it in a structure similar to feedparser output.
    Uses PRAW for authentication and API calls.
    """
    subreddit, feed_type = parse_reddit_url(feed_url)

    if not subreddit or not feed_type:
        g_logger.error(f"Could not parse subreddit/feed type from URL: {feed_url}")
        return _create_error_response(400, ValueError(f"Invalid Reddit URL format: {feed_url}"), feed_url)

    # Get PRAW Reddit client
    reddit = get_valid_reddit_client()
    if not reddit:
        g_logger.error("Could not obtain valid PRAW Reddit client.")
        return _create_error_response(401, ConnectionError("Failed to get PRAW Reddit client"), feed_url)

    praw_url = f"https://www.reddit.com/r/{subreddit}/{feed_type}"
    g_logger.info(f"Fetching {feed_type} feed for r/{subreddit} using PRAW")
    
    output = _create_success_response(praw_url)

    try:
        subreddit_obj = reddit.subreddit(subreddit)
        submissions = _get_submissions(subreddit_obj, feed_type)
        submissions_list = list(submissions)

    except (praw.exceptions.NotFound, praw.exceptions.Forbidden, praw.exceptions.RedditAPIException) as e:
        if _handle_praw_exception(e, subreddit, feed_type, praw_url, output):
            return output
        # Fall through to generic handler if not matched
    except Exception as e:
        g_logger.error(f"Unexpected error fetching Reddit data with PRAW for 'r/{subreddit}/{feed_type}': {e}", exc_info=True)
        output['bozo'] = 1
        output['bozo_exception'] = e
        output['feed']['title'] = f"r/{subreddit} - {feed_type} (Error)"
        output['feed']['link'] = praw_url
        output['status'] = 500
        return output

    # Populate feed metadata and entries
    _populate_feed_metadata(output, subreddit, feed_type, praw_url, submissions_list)
    
    for submission in submissions_list:
        entry = format_reddit_entry(submission)
        if entry:
            output['entries'].append(entry)

    if not submissions_list:
        g_logger.info(f"Note: No posts found for r/{subreddit}/{feed_type} (Subreddit might be empty or filtered).")

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
