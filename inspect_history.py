import argparse
import json
from shared import FeedHistory

def set_serializer(obj):
    """Custom serializer to convert sets to lists for JSON."""
    if isinstance(obj, set):
        return list(obj)
    return str(obj)  # Fallback for other non-serializable types

def main():
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Inspect FeedHistory data from a pickle file.")
    parser.add_argument("data_file", help="Path to the pickle file containing the history data.")
    args = parser.parse_args()

    # Load the FeedHistory data from the pickle file
    history = FeedHistory(data_file=args.data_file)

    # Print the data in a readable JSON format with custom set handling
    print(json.dumps(history.data, indent=2, default=set_serializer))

if __name__ == "__main__":
    main()