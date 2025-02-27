import argparse
import json
from shared import FeedHistory

def main():
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Inspect FeedHistory data from a pickle file.")
    parser.add_argument("data_file", help="Path to the pickle file containing the history data.")
    args = parser.parse_args()

    # Load the FeedHistory data from the pickle file
    history = FeedHistory(data_file=args.data_file)

    # Print the data in a readable JSON format
    print(json.dumps(history.data, indent=2, default=str))

if __name__ == "__main__":
    main()