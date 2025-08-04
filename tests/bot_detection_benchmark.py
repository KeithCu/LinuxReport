import re
import timeit
import random
import ahocorasick

# Common web bot user agents that should not trigger background refreshes or OpenWeather queries
BOT_PATTERNS = [
    # Google Crawlers
    "Googlebot",
    "Google-InspectionTool",
    "Google-Site-Verification",
    "Google-Extended",

    # Bing Crawlers
    "Bingbot",
    "AdIdxBot",
    "MicrosoftPreview",

    # Yandex Crawlers
    "YandexBot",
    "YandexMobileBot",
    "YandexImages",

    # AI-Related Crawlers
    "GPTBot",
    "ClaudeBot",
    "CCBot",
    "Bytespider",
    "Applebot",

    # Other Common Crawlers
    "Baiduspider",
    "DuckDuckBot",
    "AhrefsBot",
    "SemrushBot",
    "MJ12bot",
    "KeybaseBot",
    "Lemmy",
    "CookieHubScan",
    "Hydrozen.io",
    "SummalyBot",
    "DotBot",
    "Coccocbot",
    "LinuxReportDeployBot",
]

# User agents for benchmarking with 90% non-bot, 10% bot distribution
USER_AGENTS = [
    # Standard non-bot user agent (will be used 90% of the time)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    
    # Various bot user agents (will be used 10% of the time combined)
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Googlebot-Image/1.0",
    "Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "AhrefsBot/7.0; +http://ahrefs.com/robot/",
    "SemrushBot/7~bl; +http://www.semrush.com/bot.html",
    "Mozilla/5.0 (compatible; Yahoo! Slurp; http://help.yahoo.com/help/us/ysearch/slurp)",
    "DuckDuckBot/1.0; (+http://duckduckgo.com/duckduckbot.html)",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
]

# --- Pre-computation for different matching strategies ---

# For case-insensitive matching, all patterns are lowercased once.
LOWERCASE_BOT_PATTERNS = [p.lower() for p in BOT_PATTERNS]

# For the combined regex approach
COMBINED_LOWERCASE_RE_PATTERN = re.compile("|".join(re.escape(p) for p in LOWERCASE_BOT_PATTERNS))

# For the Aho-Corasick automaton
AHO_AUTOMATON = ahocorasick.Automaton()
for keyword in LOWERCASE_BOT_PATTERNS:
    AHO_AUTOMATON.add_word(keyword, keyword)
AHO_AUTOMATON.make_automaton()

# --- Bot detection functions to be benchmarked ---

def check_bot_any_in_operator(user_agent):
    """Fast, simple substring check using the 'in' operator."""
    ua_lower = user_agent.lower()
    return any(p in ua_lower for p in LOWERCASE_BOT_PATTERNS)

def check_bot_re_combined_pattern(user_agent):
    """Fastest regex approach using a single, pre-compiled, combined pattern."""
    ua_lower = user_agent.lower()
    return COMBINED_LOWERCASE_RE_PATTERN.search(ua_lower) is not None

def check_bot_ahocorasick(user_agent):
    """Highly efficient search using the Aho-Corasick algorithm."""
    ua_lower = user_agent.lower()
    # The iter method returns an iterator. We only care if it yields at least one match.
    try:
        next(AHO_AUTOMATON.iter(ua_lower))
        return True
    except StopIteration:
        return False

def run_benchmark(func, num_runs=10000):
    """Runs a benchmark for a given function."""
    # Ensure 90% non-bot, 10% bot distribution
    non_bot_ua = USER_AGENTS[0]  # First user agent is the non-bot
    bot_uas = USER_AGENTS[1:]    # Rest are bots
    
    def test_function():
        # 90% chance of non-bot, 10% chance of bot
        if random.random() < 0.9:
            return func(non_bot_ua)
        else:
            return func(random.choice(bot_uas))
    
    total_time = timeit.timeit(test_function, number=num_runs)
    # Return average time in microseconds
    return (total_time / num_runs) * 1e6

def main():
    """Main function to run and print benchmark results."""
    print("Starting bot detection benchmark...")
    print(f"Testing {len(USER_AGENTS)} user agents against {len(BOT_PATTERNS)} patterns.")
    print("-" * 40)

    functions_to_test = [
        ("check_bot_any_in_operator", check_bot_any_in_operator),
        ("check_bot_re_combined_pattern", check_bot_re_combined_pattern),
        ("check_bot_ahocorasick", check_bot_ahocorasick),
    ]

    # --- Verify correctness of each function ---
    print("Verifying function correctness...")
    all_correct = True
    for ua in USER_AGENTS:
        # Use the first function's result as the baseline for comparison
        baseline_result = functions_to_test[0][1](ua)
        for name, func in functions_to_test[1:]:
            if func(ua) != baseline_result:
                print(f"  [!] Mismatch found for UA: {ua}")
                print(f"      Baseline ({functions_to_test[0][0]}): {baseline_result}")
                print(f"      Mismatch ({name}): {func(ua)}")
                all_correct = False
    
    if all_correct:
        print("Verification complete. All methods produce identical results.")
    print("-" * 40)

    # --- Run benchmarks ---
    print("\nRunning performance benchmarks...\n")
    results = []
    # Use a higher number of runs for more stable results with the large pattern list
    num_runs = 10000
    print(f"(Each test will run {num_runs:,} times)\n")

    for name, func in functions_to_test:
        avg_time_us = run_benchmark(func, num_runs=num_runs)
        results.append((name, avg_time_us))

    results.sort(key=lambda x: x[1])

    # --- Print results ---
    print("Benchmark Results (average time per check, fastest to slowest):")
    for i, (name, avg_time) in enumerate(results):
        print(f"{i+1}. {name:<35}: {avg_time:.4f} µs")

    print("\n" + "-" * 40)
    print("Benchmark complete.")

if __name__ == "__main__":
    main()
