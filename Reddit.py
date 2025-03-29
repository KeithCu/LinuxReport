import os
import requests
import json
import time
import re
from urllib.parse import urlparse

# --- Configuration ---
# FIXME: these values with placeholders before committing to Git
REDDIT_CLIENT_ID = "your_client_id_here"
REDDIT_CLIENT_SECRET = "your_client_secret_here"
REDDIT_USERNAME = "keithcu"
REDDIT_PASSWORD = "your_reddit_password" # Needed only for initial token fetch

REDDIT_TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
REDDIT_API_BASE_URL = 'https://oauth.reddit.com'
TOKEN_FILE = 'reddit_token.json' # Simple file storage for tokens

# <platform>:<app ID>:<version string> (by /u/<reddit username>)
USER_AGENT = f'python:linuxreport.net:v1.0 (by /u/{REDDIT_USERNAME})'

# --- Token Handling ---

def get_initial_token():
    """Gets the very first token using username/password. Run this ONCE."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        raise ValueError("Missing credentials (ID, Secret, Username, Password) for initial token fetch.")

    auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    payload = {
        'grant_type': 'password',
        'username': REDDIT_USERNAME,
        'password': REDDIT_PASSWORD,
        'scope': 'read'
    }
    headers = {'User-Agent': USER_AGENT}

    print("Attempting to get initial token from Reddit...")
    response = None  # Initialize response outside try block
    try:
        response = requests.post(REDDIT_TOKEN_URL, auth=auth, data=payload, headers=headers)
        response.raise_for_status()
        token_data = response.json()
        token_data['retrieved_at'] = time.time() # Store retrieval time
        save_token(token_data)
        print("Successfully retrieved and saved initial token.")
        # IMPORTANT: Remove REDDIT_PASSWORD from environment/config after this succeeds!
        return token_data
    except requests.exceptions.RequestException as e:
        print(f"Error getting initial token: {e}")
        if response:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        return None

def save_token(token_data):
    """Saves token data to a file."""
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
        # Restrict file permissions (important on Linux/macOS)
        os.chmod(TOKEN_FILE, 0o600) # Read/write only for owner
    except IOError as e:
        print(f"Error saving token file: {e}")


def load_token():
    """Loads token data from a file."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading token file: {e}")
        return None

def refresh_token(current_token_data):
    """Uses the refresh token to get a new access token."""
    if 'refresh_token' not in current_token_data:
        print("Error: No refresh token found. Need to re-authenticate.")
        return None # Cannot refresh without a refresh token

    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET]):
         raise ValueError("Missing client credentials (ID, Secret) for refresh.")

    auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': current_token_data['refresh_token'],
    }
    headers = {'User-Agent': USER_AGENT}

    print("Attempting to refresh token...")
    response = None  # Initialize response outside try block
    try:
        response = requests.post(REDDIT_TOKEN_URL, auth=auth, data=payload, headers=headers)
        response.raise_for_status()
        new_token_data = response.json()

        # Important: Reddit might NOT return a new refresh token.
        # If it doesn't, reuse the OLD one.
        if 'refresh_token' not in new_token_data:
            new_token_data['refresh_token'] = current_token_data['refresh_token']

        new_token_data['retrieved_at'] = time.time()
        save_token(new_token_data)
        print("Successfully refreshed and saved token.")
        return new_token_data
    except requests.exceptions.RequestException as e:
        print(f"Error refreshing token: {e}")
        if response:
             print(f"Response status: {response.status_code}")
             print(f"Response body: {response.text}")
        # If refresh fails (e.g., invalid refresh token), may need full re-auth
        if response and response.status_code in [400, 401]:
             print("Refresh token might be invalid. Manual re-authentication required.")
             # Optionally delete the bad token file here
             # if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
        return None

def get_valid_token():
    """Gets a valid access token, refreshing if necessary."""
    token_data = load_token()

    if not token_data:
        print("No token file found. Attempting initial fetch.")
        token_data = get_initial_token()
        if not token_data:
            return None # Failed initial fetch

    # Check if token is expired or close to expiring (e.g., within 60 seconds)
    expires_in = token_data.get('expires_in', 3600) # Default to 1 hour if missing
    retrieved_at = token_data.get('retrieved_at', 0)
    if time.time() > retrieved_at + expires_in - 60:
        print("Token expired or nearing expiry, attempting refresh.")
        token_data = refresh_token(token_data)

    return token_data.get('access_token') if token_data else None

# --- Example API Call ---

def get_subscribed_subreddits(access_token):
    """Example API call to get user's subscribed subreddits."""
    if not access_token:
        print("Cannot make API call: No valid access token.")
        return None

    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': USER_AGENT
    }
    api_url = f"{REDDIT_API_BASE_URL}/subreddits/mine/subscriber"
    params = {'limit': 5} # Get first 5

    print(f"Fetching subscribed subreddits from {api_url}...")
    try:
        response = requests.get(api_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API call failed: {e}")
        if response:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
            if response.status_code == 401:
                print("API call failed with 401 (Unauthorized). Token might be invalid/revoked even after refresh attempt.")
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
            print(f"Warning: Invalid subreddit format found: {subreddit}")
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
        print(f"Error parsing URL '{url}': {e}")
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
             print(f"Warning: Could not parse timestamp {created_utc}")
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

    Args:
        feed_url (str): The Reddit URL (e.g., "https://www.reddit.com/r/linux/hot/.rss")

    Returns:
        dict: A dictionary mimicking feedparser structure, or None on critical failure.
              Contains 'feed' and 'entries' keys. 'bozo' key indicates non-critical errors.
    """
    subreddit, feed_type = parse_reddit_url(feed_url)

    if not subreddit or not feed_type:
        print(f"Error: Could not parse subreddit/feed type from URL: {feed_url}")
        # Return a structure indicating failure, similar to feedparser's bozo=1
        return {
            'bozo': 1,
            'bozo_exception': ValueError(f"Invalid Reddit URL format: {feed_url}"),
            'feed': {},
            'entries': [],
            'status': 400, # Indicate bad request
            'href': feed_url
        }

    access_token = get_valid_token() # Assumes this function exists and works
    if not access_token or access_token == "DUMMY_TOKEN": # Added dummy check for testing
        print("Error: Could not obtain valid Reddit access token.")
        return {
            'bozo': 1,
            'bozo_exception': ConnectionError("Failed to get Reddit access token"),
            'feed': {},
            'entries': [],
            'status': 401, # Indicate auth failure
            'href': feed_url
        }

    # Construct the API endpoint path
    api_path = f"/r/{subreddit}/{feed_type}"
    api_url = f"{REDDIT_API_BASE_URL}{api_path}" # Use oauth.reddit.com

    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': USER_AGENT
    }
    # Standard Reddit API limit for listings
    params = {'limit': 25}

    print(f"Fetching {feed_type} feed for r/{subreddit} from API: {api_url}")
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
         print(f"Error: {msg}")
         output['bozo'] = 1
         output['bozo_exception'] = requests.exceptions.Timeout(msg)
         return output # Return partial structure with error info
    except requests.exceptions.HTTPError as e:
         msg = f"HTTP error fetching Reddit API data: {e}"
         print(f"Error: {msg}")
         if response:  # Added check to prevent potential error
             print(f"Response: {response.text[:500]}") # Log part of the response body
         output['bozo'] = 1
         output['bozo_exception'] = e
         # Attempt to parse feed info even on error if possible (e.g. 404)
         output['feed']['title'] = f"r/{subreddit} - {feed_type} (Error)"
         output['feed']['link'] = f"https://www.reddit.com/r/{subreddit}/{feed_type}"
         return output # Return partial structure with error info
    except requests.exceptions.RequestException as e:
        # Catch other network/request related errors
        msg = f"Network error fetching Reddit API data: {e}"
        print(f"Error: {msg}")
        output['bozo'] = 1
        output['bozo_exception'] = e
        return output # Return partial structure with error info
    except json.JSONDecodeError as e:
         msg = f"Error decoding JSON response from {api_url}: {e}"
         print(f"Error: {msg}")
         if response:  # Add null check here
             print(f"Response Text: {response.text[:500]}") # Log problematic text
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
        print(f"Note: No posts found for r/{subreddit}/{feed_type} (Subreddit might be empty or filtered).")
        # Still a valid response, just no entries. bozo remains 0.

    return output

# --- Main Execution Logic ---
if __name__ == '__main__':
    # Ensure client credentials are set
    if REDDIT_CLIENT_ID == "your_client_id_here" or REDDIT_CLIENT_SECRET == "your_client_secret_here":
        print("Error: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be properly configured.")
    else:
        # Get a valid token (loads existing, fetches initial, or refreshes)
        current_access_token = get_valid_token()

        if current_access_token:
            print("\nSuccessfully obtained a valid access token.")

            # Now you can use the current_access_token to make API calls
            subreddits_data = get_subscribed_subreddits(current_access_token)

            if subreddits_data and 'data' in subreddits_data and 'children' in subreddits_data['data']:
                print("\nFirst few subscribed subreddits:")
                for sub in subreddits_data['data']['children']:
                    print(f"- {sub['data']['display_name']}")
            else:
                print("\nCould not retrieve subscribed subreddits.")
        else:
            print("\nFailed to obtain a valid access token. Cannot proceed.")

