"""
Reddit.py

Handles Reddit API authentication, token management, and fetching Reddit feeds in a feedparser-compatible format for the LinuxReport project.
"""

import getpass
import json
# Standard library imports
import os
import re
import time
from urllib.parse import urlparse

# Third-party imports
import requests

# Local imports
from app import g_logger

# --- Configuration ---
# Credentials are now handled via the token file or initial prompt

REDDIT_TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
REDDIT_API_BASE_URL = 'https://oauth.reddit.com'
TOKEN_FILE = 'reddit_token.json' # Simple file storage for tokens

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

# USER_AGENT is now constructed dynamically where needed, using the username from token data

# --- Token Handling ---

def get_initial_token(client_id, client_secret, username, password):
    """Gets the very first token using user-provided credentials."""
    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    payload = {
        'grant_type': 'password',
        'username': username,
        'password': password,
        'scope': 'read' # Request only necessary permissions
    }
    # Construct user agent here for the initial request
    user_agent = f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{username})'
    headers = {'User-Agent': user_agent}

    g_logger.info("Attempting to get initial token from Reddit...")
    response = None
    try:
        response = requests.post(REDDIT_TOKEN_URL, auth=auth, data=payload, headers=headers)
        response.raise_for_status()
        token_data = response.json()
        token_data['retrieved_at'] = time.time()
        # Store necessary credentials for refresh alongside tokens
        token_data['client_id'] = client_id
        token_data['client_secret'] = client_secret # Consider security implications
        token_data['username'] = username
        save_token(token_data)
        g_logger.info("Successfully retrieved and saved initial token and credentials.")
        return token_data
    except requests.exceptions.RequestException as e:
        g_logger.error(f"Error getting initial token: {e}")
        if response is not None:
            g_logger.error(f"Response status: {response.status_code}")
            g_logger.error(f"Response body: {response.text}")
        return None

def save_token(token_data):
    """Saves token data (including client ID/secret/username) to a file."""
    try:
        # Ensure sensitive data like client_secret isn't inadvertently logged
        # In a real app, consider encrypting TOKEN_FILE or using secure storage
        g_logger.info(f"Saving token data for user '{token_data.get('username', 'N/A')}' to {TOKEN_FILE}")
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=4) # Add indent for readability
        os.chmod(TOKEN_FILE, 0o600) # Read/write only for owner
    except IOError as e:
        g_logger.error(f"Error saving token file '{TOKEN_FILE}': {e}")
    except Exception as e: # Catch other potential errors like permission issues
        g_logger.error(f"An unexpected error occurred while saving the token: {e}")


def load_token():
    """Loads token data (including client ID/secret/username) from a file."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
            # Basic validation: check for essential keys
            if not all(k in token_data for k in ['access_token', 'refresh_token', 'client_id', 'client_secret', 'username']):
                 g_logger.warning(f"Token file '{TOKEN_FILE}' is missing essential keys. Re-authentication may be required.")
                 # Optionally return None or handle partial data
            return token_data
    except (IOError, json.JSONDecodeError) as e:
        g_logger.error(f"Error loading or parsing token file '{TOKEN_FILE}': {e}")
        return None
    except Exception as e: # Catch other potential errors
        g_logger.error(f"An unexpected error occurred while loading the token: {e}")
        return None

def refresh_token(current_token_data):
    """Uses the refresh token to get a new access token."""
    refresh_tok = current_token_data.get('refresh_token')
    client_id = current_token_data.get('client_id')
    client_secret = current_token_data.get('client_secret')
    username = current_token_data.get('username', 'unknown_user') # Get username for user agent

    if not refresh_tok:
        g_logger.error("Error: No refresh token found in stored data. Need to re-authenticate.")
        return None
    if not client_id or not client_secret:
         g_logger.error("Error: Missing client credentials (ID, Secret) in stored data for refresh.")
         return None # Cannot refresh without credentials

    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_tok,
    }
    # Construct user agent using username from token data
    user_agent = f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{username})'
    headers = {'User-Agent': user_agent}

    g_logger.info("Attempting to refresh token...")
    response = None
    try:
        response = requests.post(REDDIT_TOKEN_URL, auth=auth, data=payload, headers=headers)
        response.raise_for_status()
        new_token_data = response.json()

        # Preserve essential data from the old token if not returned in refresh
        if 'refresh_token' not in new_token_data:
            new_token_data['refresh_token'] = refresh_tok # IMPORTANT: Reuse old refresh token
        new_token_data['client_id'] = client_id
        new_token_data['client_secret'] = client_secret
        new_token_data['username'] = username
        new_token_data['retrieved_at'] = time.time()

        save_token(new_token_data)
        g_logger.info("Successfully refreshed and saved token.")
        return new_token_data
    except requests.exceptions.RequestException as e:
        g_logger.error(f"Error refreshing token: {e}")
        if response is not None:
            g_logger.error(f"Response status: {response.status_code}")
            g_logger.error(f"Response body: {response.text}")
        if response is not None and response.status_code in [400, 401]:
            g_logger.warning("Refresh token might be invalid or expired. Manual re-authentication required.")
            # Consider deleting the invalid token file to force re-auth next time
            # try:
            #     os.remove(TOKEN_FILE)
            #     print(f"Removed potentially invalid token file: {TOKEN_FILE}")
            # except OSError as rm_err:
            #     print(f"Could not remove token file: {rm_err}")
        return None

def get_valid_token():
    """
    Gets valid token data (including access_token and username),
    prompting for initial credentials if needed, or refreshing if expired.
    Returns:
        tuple: (access_token, username) or (None, None) on failure.
    """
    token_data = load_token()

    if not token_data:
        g_logger.info(f"No token file found ('{TOKEN_FILE}') or file is invalid.")
        g_logger.info("Please provide your Reddit API credentials for initial setup.")
        try:
            client_id = input("Enter your Reddit Client ID: ").strip()
            client_secret = getpass.getpass("Enter your Reddit Client Secret: ").strip()
            username = input("Enter your Reddit Username: ").strip()
            password = getpass.getpass("Enter your Reddit Password (only needed once): ").strip()

            if not all([client_id, client_secret, username, password]):
                g_logger.error("Error: All credentials must be provided for initial setup.")
                return None, None

            token_data = get_initial_token(client_id, client_secret, username, password)
            # Clear password from memory immediately after use
            del password
            if not token_data:
                g_logger.error("Failed to obtain initial token.")
                return None, None # Failed initial fetch
            g_logger.info("Initial token fetch successful.")
        except EOFError: # Handle running in non-interactive environment
             g_logger.error("\nError: Cannot prompt for credentials in non-interactive mode and no token file found.")
             return None, None
        except Exception as e: # Catch other potential input errors
             g_logger.error(f"\nAn error occurred during credential input: {e}")
             return None, None


    # Check if token is expired or close to expiring (e.g., within 60 seconds)
    expires_in = token_data.get('expires_in', 3600) # Default to 1 hour
    retrieved_at = token_data.get('retrieved_at', 0)
    current_time = time.time()

    if current_time > retrieved_at + expires_in - 60:
        g_logger.info("Token expired or nearing expiry, attempting refresh.")
        refreshed_token_data = refresh_token(token_data)
        if not refreshed_token_data:
            g_logger.error("Failed to refresh token. Manual intervention may be required.")
            # Depending on policy, could delete token file here or just return failure
            return None, None
        token_data = refreshed_token_data # Use the new token data

    # Return the access token and username from the (potentially refreshed) data
    access_token = token_data.get('access_token')
    username = token_data.get('username')

    if not access_token or not username:
        g_logger.error("Error: Could not retrieve valid access token or username from token data.")
        return None, None

    return access_token, username

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
    except Exception as e:
        g_logger.error(f"Error parsing URL '{url}': {e}")
        return None, None


def format_reddit_entry(post_wrapper):
    """Formats a single Reddit API post into a feedparser-like entry dict."""
    if post_wrapper.get('kind') != 't3': # t3 is the 'Thing' kind for posts
        return None
    post_data = post_wrapper.get('data', {})
    if not post_data:
        return None

    entry = {}
    entry['title'] = post_data.get('title', '')
    entry['author'] = post_data.get('author', '')
    # Reddit 'permalink' is relative, needs domain prepended
    entry['link'] = f"https://www.reddit.com{post_data.get('permalink', '')}" if post_data.get('permalink') else ''
    # Use Reddit's 'name' (e.g., t3_xxxxx) as the stable ID
    entry['id'] = post_data.get('name', entry['link']) # Fallback to link if name missing

    # Summary & Content (Mimic feedparser structure)
    summary = post_data.get('selftext', '') # Markdown version
    content_html = post_data.get('selftext_html') # HTML version, often needs decoding

    # If not a self-post and summary is empty, use the external URL as summary
    if not post_data.get('is_self', False) and not summary:
        summary = post_data.get('url', '') # Link posts point to external URL here
    entry['summary'] = summary

    # feedparser 'content' is often a list of dicts
    entry['content'] = []
    if content_html:
         # Note: Reddit's selftext_html is often HTML-escaped, real feedparser might handle better
        entry['content'].append({
             'type': 'text/html',
             'language': None,
             'base': entry['link'],
             'value': content_html # May need html.unescape() depending on usage
         })
    elif summary and post_data.get('is_self', False): # Only add plain text content for self posts
        entry['content'].append({
             'type': 'text/plain',
             'language': None,
             'base': entry['link'],
             'value': summary
        })

    # Time parsing - Reddit provides UTC timestamp
    created_utc = post_data.get('created_utc')
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
    entry['reddit_score'] = post_data.get('score')
    entry['reddit_num_comments'] = post_data.get('num_comments')
    # Provide thumbnail URL only if it's a valid image URL
    thumb = post_data.get('thumbnail')
    entry['reddit_thumbnail'] = thumb if thumb and thumb.startswith('http') else None
    entry['reddit_url'] = post_data.get('url') # The external link for link posts
    entry['reddit_domain'] = post_data.get('domain')
    entry['reddit_is_self'] = post_data.get('is_self', False)
    entry['reddit_subreddit'] = post_data.get('subreddit')

    return entry


def fetch_reddit_feed_as_feedparser(feed_url):
    """
    Fetches data from Reddit API based on an RSS-like URL
    and returns it in a structure similar to feedparser output.
    Requires a valid token obtained via get_valid_token().
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

    # Get token AND username
    access_token, username = get_valid_token()
    if not access_token or not username:
        g_logger.error("Could not obtain valid Reddit access token and username.")
        # Return structure indicating auth failure
        return {
            'bozo': 1,
            'bozo_exception': ConnectionError("Failed to get Reddit access token/username"),
            'feed': {},
            'entries': [],
            'status': 401, # Indicate auth failure
            'href': feed_url
        }

    # Construct User-Agent using the retrieved username
    user_agent = f'python:{extract_domain_from_url_images(URL_IMAGES)}:v1.0 (by /u/{username})'

    # Construct the API endpoint path
    api_path = f"/r/{subreddit}/{feed_type}"
    api_url = f"{REDDIT_API_BASE_URL}{api_path}" # Use oauth.reddit.com

    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': user_agent # Use dynamically generated user agent
    }
    params = {'limit': 25} # Standard Reddit API limit

    g_logger.info(f"Fetching {feed_type} feed for r/{subreddit} from API: {api_url}")
    output = {
        'bozo': 0, # Assume success unless errors occur
        'bozo_exception': None,
        'feed': {},
        'entries': [],
        'headers': {},
        'href': api_url,
        'status': 0, # Will be updated after request
        'encoding': 'utf-8', # Default, update from response
        'version': 'reddit_api_v1' # Custom version identifier
    }

    response = None  # Initialize response outside try block
    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=15) # Increased timeout
        output['status'] = response.status_code
        output['headers'] = dict(response.headers)
        output['encoding'] = response.encoding or 'utf-8'

        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        api_data = response.json()

    except requests.exceptions.Timeout:
        msg = f"Request timed out for {api_url}"
        g_logger.error(f"Error: {msg}")
        output['bozo'] = 1
        output['bozo_exception'] = requests.exceptions.Timeout(msg)
        return output # Return partial structure with error info
    except requests.exceptions.HTTPError as e:
        msg = f"HTTP error fetching Reddit API data: {e}"
        g_logger.error(f"Error: {msg}")
        if response:  # Added check to prevent potential error
            g_logger.error(f"Response: {response.text[:500]}") # Log part of the response body
        output['bozo'] = 1
        output['bozo_exception'] = e
        # Attempt to parse feed info even on error if possible (e.g. 404)
        output['feed']['title'] = f"r/{subreddit} - {feed_type} (Error)"
        output['feed']['link'] = f"https://www.reddit.com/r/{subreddit}/{feed_type}"
        return output # Return partial structure with error info
    except requests.exceptions.RequestException as e:
        # Catch other network/request related errors
        msg = f"Network error fetching Reddit API data: {e}"
        g_logger.error(f"Error: {msg}")
        output['bozo'] = 1
        output['bozo_exception'] = e
        return output # Return partial structure with error info
    except json.JSONDecodeError as e:
        msg = f"Error decoding JSON response from {api_url}: {e}"
        g_logger.error(f"Error: {msg}")
        if response:  # Add null check here
            g_logger.error(f"Response Text: {response.text[:500]}") # Log problematic text
        output['bozo'] = 1
        output['bozo_exception'] = e
        return output # Return partial structure with error info

    # --- Format the successful output ---

    # Populate feed metadata
    output['feed']['title'] = f"r/{subreddit} - {feed_type}"
    # Link to the human-viewable Reddit page for the feed
    output['feed']['link'] = f"https://www.reddit.com/r/{subreddit}/{feed_type}"
    output['feed']['links'] = [{'rel': 'alternate', 'type': 'text/html', 'href': output['feed']['link']}]
    output['feed']['subtitle'] = f"Posts from r/{subreddit} sorted by {feed_type} via Reddit API"
    output['feed']['language'] = 'en' # Assume English, Reddit API doesn't specify

    # Use the timestamp of the newest post as the feed's updated time
    # Use dict.get() with default values to avoid KeyErrors
    data_obj = api_data.get('data', {})
    posts = data_obj.get('children', [])
    if posts:
        first_post_data = posts[0].get('data', {})
        created_utc = first_post_data.get('created_utc')
        if created_utc:
            try:
                updated_parsed = time.gmtime(float(created_utc))
                output['feed']['updated_parsed'] = updated_parsed
                output['feed']['updated'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT', updated_parsed)
            except (ValueError, TypeError):
                pass # Ignore if timestamp is bad

    # Populate entries
    for post_wrapper in posts:
        entry = format_reddit_entry(post_wrapper)
        if entry:
            output['entries'].append(entry)

    if not posts and api_data.get('kind') == 'Listing':
        g_logger.info(f"Note: No posts found for r/{subreddit}/{feed_type} (Subreddit might be empty or filtered).")
        # Still a valid response, just no entries. bozo remains 0.

    return output

# --- Main Execution Logic ---
if __name__ == '__main__':
    g_logger.info("Attempting to ensure a valid Reddit token exists...")
    # This call will handle loading, prompting for initial creds, or refreshing
    token, user = get_valid_token()

    if token and user:
        g_logger.info(f"\nSuccessfully obtained a valid token for user: {user}.")
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
        g_logger.error("\nFailed to obtain a valid Reddit token. Cannot proceed with API calls.")
        g_logger.error(f"Check for errors above. If it's the first run, ensure you provide correct credentials when prompted.")
        g_logger.error(f"Make sure the token file '{TOKEN_FILE}' is writable if it needs to be created/updated.")
