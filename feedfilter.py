
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

