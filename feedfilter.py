import difflib

from shared import g_c


# Google boosts CNN and other fake news, so filter it:
# https://www.rt.com/usa/459233-google-liberal-bias-news-study/
# CNN is fake: https://www.realclearpolitics.com/video/2019/03/26/glenn_greenwald_cnn_and_msnbc_are_like_state_tv_with_ex-intel_officials_as_contributors.html
def prefilter_news(url, feedinfo):
    if url == "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984":
        entries = feedinfo['entries'].copy()

        for entry in feedinfo['entries']:
            if entry.link.find("cnn") > -1:
                entries.remove(entry)

        return entries
    elif url == "http://www.independent.co.uk/topic/coronavirus/rss":
        entries = feedinfo['entries'].copy()

        #Tire of angry anti-Trump articles.
        for entry in feedinfo['entries']:
            if entry.title.find("Trump") > -1:
                entries.remove(entry)

        return entries

    return feedinfo['entries']

#If we've seen this title in other feeds, then filter it.
def filter_similar_titles(url, entries):
    feed_alt = None

    if url == "https://www.reddit.com/r/Coronavirus/rising/.rss":
        feed_alt = g_c.get("https://www.reddit.com/r/China_Flu/rising/.rss")

    if url == "https://www.reddit.com/r/China_Flu/rising/.rss":
        feed_alt = g_c.get("https://www.reddit.com/r/Coronavirus/rising/.rss")

    if feed_alt:
        entries_c = entries.copy()

        for entry in entries_c:
            entry_words = sorted(entry.title.split())
            for entry_alt in feed_alt.entries:
                entry_alt_words = sorted(entry_alt.title.split())
                similarity = difflib.SequenceMatcher(None, entry_words, entry_alt_words).ratio()
                if similarity > 0.7:  # Adjust the threshold as needed
                    print(f"Similar title: 1: {entry.title}, 2: {entry_alt.title}, similarity: {similarity}.")
                    try:  # Entry could have been removed by another similar title
                        entries.remove(entry)
                    except:
                        pass
                    else:
                        print("Deleted title.")

    return entries

def merge_entries(new_entries, old_entries, title_threshold=0.85):
    """
    Merge two lists of feed entries, preserving order and avoiding duplicates.
    Two entries are considered the same if:
      - They share the same link.
    
    New entries take precedence over cached ones.
    """
    merged = []
    seen_links = set()
    new_titles = []  # to compare against old titles

    # Process new entries first.
    for entry in new_entries:
        # Get unique key and title. (Assumes entries are dicts.)
        key = entry.get('link')
        title = entry.get('title')
        if key:
            seen_links.add(key)
        if title:
            new_titles.append(title)
        merged.append(entry)

    # Append old entries only if they’re not already represented.
    for entry in old_entries:
        key = entry.get('link')
        title = entry.get('title')
        # Skip if the link already exists.
        if key and key in seen_links:
            continue

        merged.append(entry)

    return merged