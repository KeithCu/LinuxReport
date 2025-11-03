#!/bin/bash
# update_all_logos.sh
# Updates themed logos for all LinuxReport sites
#
# Usage: ./update_all_logos.sh "Halloween"
#        ./update_all_logos.sh "Christmas"
#        ./update_all_logos.sh "Fall"

# Don't use set -e, we want to continue processing even if one fails

# Check if theme argument is provided
if [ -z "$1" ]; then
    echo "Error: Theme argument required"
    echo "Usage: $0 \"THEME_NAME\""
    echo "Example: $0 \"Halloween\""
    echo "Example: $0 \"Christmas\""
    echo "Example: $0 \"Fall\""
    exit 1
fi

THEME="$1"

# Base directory for the script (assuming all sites share the same venv and script location)
BASE_DIR="/srv/http/LinuxReport2"
SCRIPT_NAME="generate_themed_logo.py"

# Activate virtual environment
if [ -f "$BASE_DIR/venv/bin/activate" ]; then
    source "$BASE_DIR/venv/bin/activate"
else
    echo "Error: Virtual environment not found at $BASE_DIR/venv/bin/activate"
    exit 1
fi

# Source configuration if it exists
if [ -f "/etc/update_headlines.conf" ]; then
    source /etc/update_headlines.conf
fi

# Map directories to report types
# Format: "directory:report_type"
declare -A DIR_REPORT_MAP=(
    ["/srv/http/LinuxReport2"]="linux"
    ["/srv/http/CovidReport2"]="covid"
    ["/srv/http/trumpreport"]="trump"
    ["/srv/http/aireport"]="ai"
    ["/srv/http/spacereport"]="space"
    ["/srv/http/pvreport"]="pv"
    ["/srv/http/robotreport"]="robot"
)

echo "=========================================="
echo "Updating themed logos for all reports"
echo "Theme: $THEME"
echo "=========================================="
echo ""

# Track success/failure
SUCCESS_COUNT=0
FAILURE_COUNT=0
FAILED_REPORTS=()

# Process each directory
for dir in "${!DIR_REPORT_MAP[@]}"; do
    report_type="${DIR_REPORT_MAP[$dir]}"
    
    echo "----------------------------------------"
    echo "Processing: $report_type report"
    echo "Directory: $dir"
    echo "----------------------------------------"
    
    # Check if directory exists
    if [ ! -d "$dir" ]; then
        echo "Warning: Directory not found: $dir"
        echo "Skipping $report_type report..."
        echo ""
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_REPORTS+=("$report_type (directory not found)")
        continue
    fi
    
    # Check if script exists in base directory
    if [ ! -f "$BASE_DIR/$SCRIPT_NAME" ]; then
        echo "Error: $SCRIPT_NAME not found at $BASE_DIR/$SCRIPT_NAME"
        echo "Please ensure the script exists in the base directory."
        exit 1
    fi
    
    # Change to directory (for logo files and settings files)
    cd "$dir" || {
        echo "Error: Failed to change to directory $dir"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_REPORTS+=("$report_type (cd failed)")
        continue
    }
    
    # Run the logo generation script from base directory
    if python "$BASE_DIR/$SCRIPT_NAME" --report "$report_type" --custom-prompt "$THEME"; then
        echo "✓ Successfully updated $report_type logo"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "✗ Failed to update $report_type logo"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_REPORTS+=("$report_type")
    fi
    
    echo ""
done

# Deactivate virtual environment
deactivate

# Print summary
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Theme: $THEME"
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAILURE_COUNT"
echo ""

if [ $FAILURE_COUNT -gt 0 ]; then
    echo "Failed reports:"
    for report in "${FAILED_REPORTS[@]}"; do
        echo "  - $report"
    done
    echo ""
    exit 1
else
    echo "All logos updated successfully!"
    exit 0
fi

