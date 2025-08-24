"""
Logging.py

Centralized logging configuration and utilities for LinuxReport.
Supports cross-platform line ending handling for log rotation.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import sys
import logging

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Logging configuration
# LOG_LEVEL options: DEBUG, INFO, WARNING, ERROR, CRITICAL
# - DEBUG: Most verbose - shows everything including full AI responses, article lists, etc.
# - INFO: Default level - shows main process steps, counts, success/failure messages
# - WARNING: Shows warnings and errors only
# - ERROR: Shows only errors
# - CRITICAL: Shows only critical errors
# Note: Each level includes all levels above it (INFO includes WARNING, ERROR, CRITICAL)
LOG_LEVEL = "INFO"  # Change to "DEBUG" for maximum verbosity

# Get the directory where this script is located and use it for the log file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "linuxreport.log")  # Log file in the same directory as this script

def _rotate_log_file():
    """
    Rotate the log file to keep only the last 1MB of content.
    Ensures truncation happens at line boundaries to maintain log integrity.
    Works on both Linux (LF) and Windows (CRLF) systems.
    """
    max_size_bytes = 1024 * 1024  # 1MB

    try:
        if not os.path.exists(LOG_FILE):
            return  # File doesn't exist yet, nothing to rotate

        # Check file size
        file_size = os.path.getsize(LOG_FILE)
        if file_size <= max_size_bytes:
            return  # File is small enough, no rotation needed

        # Read the file from the end to find where to truncate
        with open(LOG_FILE, 'rb') as f:
            # Move to 1MB from the end
            f.seek(-max_size_bytes, 2)

            # Read from that position to the end
            remaining_content = f.read()

        # Find the first complete line boundary (works with both LF and CRLF)
        # Look for both \n (Unix/Linux) and \r\n (Windows) line endings
        first_newline_pos = -1

        # Try to find \r\n first (Windows line ending)
        crlf_pos = remaining_content.find(b'\r\n')
        if crlf_pos != -1:
            first_newline_pos = crlf_pos + 2  # Include the full \r\n
        else:
            # Look for just \n (Unix/Linux line ending)
            lf_pos = remaining_content.find(b'\n')
            if lf_pos != -1:
                first_newline_pos = lf_pos + 1  # Include the \n

        if first_newline_pos != -1:
            # Start from the first complete line
            content_to_keep = remaining_content[first_newline_pos:]
        else:
            # No line ending found, keep the whole remaining content
            content_to_keep = remaining_content

        # Write the truncated content back to the file
        with open(LOG_FILE, 'wb') as f:
            f.write(content_to_keep)

        print(f"Log file rotated: kept last {len(content_to_keep)} bytes")

    except Exception as e:
        # Don't fail the application if log rotation fails
        print(f"Warning: Failed to rotate log file: {e}")

def _setup_logging():
    """Configure logging for the application."""
    # Rotate log file if it's too large
    _rotate_log_file()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),  # 'a' for append mode
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Suppress HTTP client debug messages
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # Create logger instance
    logger = logging.getLogger(__name__)

    # Log startup information
    logger.info(f"Starting Flask application with LOG_LEVEL={LOG_LEVEL}")
    logger.info(f"Log file: {LOG_FILE}")

    return logger

# Create the global logger instance
g_logger = _setup_logging()
