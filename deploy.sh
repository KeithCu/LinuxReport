#!/bin/bash

# =============================================================================
# CONFIGURATION - Edit these values as needed
# =============================================================================

# Web server service name (change this if using nginx, gunicorn, etc.)
WEB_SERVER_SERVICE="httpd"

# URLs for each service
declare -A urls=(
    ["LinuxReport2"]="https://linuxreport.net"
    ["CovidReport2"]="https://covidreport.org"
    ["aireport"]="https://aireport.keithcu.com"
    ["trumpreport"]="https://trumpreport.info"
    ["pvreport"]="https://pvreport.org"
    ["spacereport"]="https://news.spaceelevatorwiki.com"
)

# =============================================================================
# FUNCTIONS
# =============================================================================

# Function to change ownership for a directory
chown_directory() {
    local dir=$1
    
    echo "Changing ownership for $dir..."
    cd "$dir"
    sudo chown -R http:http *
    cd ..
}

# Function to wake up a site with curl
wake_up_site() {
    local dir=$1
    local url=$2
    local output_file="/tmp/deploy_${dir}.out"
    local start_time=$(date +%s.%3N)
    
    # Clear output file
    > "$output_file"
    
    # Format site name for display
    local site_name=$(echo "$dir" | sed 's/Report2/Report/g' | sed 's/report/Report/g')
    
    # Print when this task starts
    echo "🔄 $site_name | Starting at ${start_time}s" >> "$output_file"
    
    max_attempts=5
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # Make the request with User-Agent header
        response=$(curl -s -w "HTTP_STATUS:%{http_code}" -H "User-Agent: Deploy-Script/1.0" --connect-timeout 10 --max-time 10 "$url")
        http_status=$(echo "$response" | grep "HTTP_STATUS:" | cut -d: -f2)
        response_content=$(echo "$response" | grep -v "HTTP_STATUS:")
        
        # Extract title from line 9 (similar to Python version)
        title_line=$(echo "$response_content" | sed -n '9p')
        title=$(echo "$title_line" | sed 's/<title>//' | sed 's/<\/title>//' | xargs)
        
        # Check if we got a successful response with content
        if [[ -n "$title" ]]; then
            status_icon="✅"
            status_text="SUCCESS"
            break
        elif [[ "$http_status" == "000" ]]; then
            status_icon="❌"
            status_text="CONNECTION FAILED"
        else
            status_icon="⚠️"
            status_text="EMPTY RESPONSE"
        fi
        
        if [ $attempt -lt $max_attempts ]; then
            attempt=$((attempt + 1))
            sleep 3
        else
            status_icon="💥"
            status_text="FAILED"
            title="No title found"
            break
        fi
    done
    
    # Calculate duration
    local end_time=$(date +%s.%3N)
    local duration=$(echo "$end_time - $start_time" | bc -l)
    
    # Format the output in columns
    printf "%s %-15s | %-3s | %-40s | %.2fs\n" "$status_icon" "$site_name" "$http_status" "$title" "$duration" >> "$output_file"
    
    # Return success status
    if [[ "$status_text" == "SUCCESS" ]]; then
        echo "SUCCESS" >> "$output_file"
    else
        echo "FAILED" >> "$output_file"
    fi
}

# Function to wake up all sites for a specific round
wake_up_sites_round() {
    local round_name=$1
    local round_number=$2
    
    echo "Step $round_number: $round_name..."
    echo "===================================================================================================="
    printf "%-15s | %-3s | %-40s | %s\n" "Site" "Status" "Title" "Duration"
    echo "----------------------------------------------------------------------------------------------------"
    
    local start_time=$(date +%s.%3N)
    
    # Submit all tasks to background
    for dir in "${!urls[@]}"; do
        url="${urls[$dir]}"
        wake_up_site "$dir" "$url" &
        sleep 0.05  # 50ms delay between submissions (like Python version)
    done
    
    # Monitor progress in real-time
    local completed=0
    local total=${#urls[@]}
    local success_count=0
    
    while [ $completed -lt $total ]; do
        completed=0
        success_count=0
        for dir in "${!urls[@]}"; do
            output_file="/tmp/deploy_${dir}.out"
            if [[ -f "$output_file" ]]; then
                # Check if we have a final result (contains SUCCESS or FAILED at the end)
                if grep -q "^SUCCESS$" "$output_file" || grep -q "^FAILED$" "$output_file"; then
                    completed=$((completed + 1))
                    # Display result if we haven't shown it yet
                    if ! grep -q "^DISPLAYED:" "$output_file"; then
                        # Get the formatted line (second to last line)
                        local result_line=$(tail -n 2 "$output_file" | head -n 1)
                        echo "$result_line"
                        echo "DISPLAYED:" >> "$output_file"  # Mark as displayed
                        
                        # Count successes
                        if grep -q "^SUCCESS$" "$output_file"; then
                            success_count=$((success_count + 1))
                        fi
                    fi
                fi
            fi
        done
        
        if [ $completed -lt $total ]; then
            echo -n "⏳ Waiting for sites... ($completed/$total complete) "
            sleep 1
            echo ""
        fi
    done
    
    local end_time=$(date +%s.%3N)
    local duration=$(echo "$end_time - $start_time" | bc -l)
    
    echo "----------------------------------------------------------------------------------------------------"
    echo "✅ $success_count/$total sites deployed successfully!"
    printf "⏱️  Total time: %.2f seconds\n" "$duration"
    echo "===================================================================================================="
    
    # Return values (we'll use global variables since bash functions can't return multiple values)
    ROUND_SUCCESS_COUNT=$success_count
    ROUND_DURATION=$duration
}

# Function to wake up all sites with two rounds
wake_up_all_sites_concurrent() {
    # First round
    wake_up_sites_round "Waking up all sites" 3
    local first_success=$ROUND_SUCCESS_COUNT
    local first_duration=$ROUND_DURATION
    
    # Wait 1 second after initial warm-up
    echo ""
    echo "⏳ Waiting 1 second before second round..."
    sleep 1
    
    # Second round
    wake_up_sites_round "Second round - waking up all sites again" 4
    local second_success=$ROUND_SUCCESS_COUNT
    local second_duration=$ROUND_DURATION
}

# Function to warm up sites only
warm_up_sites_only() {
    echo "🔥 Warming up all sites only..."
    echo "===================================================================================================="
    
    # Single round of warm-up
    wake_up_sites_round "Warming up all sites" 1
    local success_count=$ROUND_SUCCESS_COUNT
    local duration=$ROUND_DURATION
    
    printf "🔥 Warm-up complete! %d/%d sites warmed up in %.2f seconds\n" "$success_count" "${#urls[@]}" "$duration"
}

# Function to parse command line arguments
parse_arguments() {
    WARMUP_ONLY=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --warmup-only)
                WARMUP_ONLY=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --warmup-only    Only warm up sites without chown or restart"
                echo "  -h, --help       Show this help message"
                echo ""
                echo "Description:"
                echo "  Deploy and warm up sites with enhanced timing and status reporting"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

# Parse command line arguments
parse_arguments "$@"

if [[ "$WARMUP_ONLY" == true ]]; then
    # Just warm up sites
    warm_up_sites_only
else
    # Full deployment
    overall_start=$(date +%s.%3N)
    
    # Step 1: Change ownership for all directories
    echo "Step 1: Changing ownership for all directories..."
    for dir in "${!urls[@]}"; do
        chown_directory "$dir"
    done
    
    # Step 2: Restart web server
    echo "Step 2: Restarting web server..."
    sudo systemctl restart "$WEB_SERVER_SERVICE"
    sleep 0.25
    
    # Step 3: Wake up all sites concurrently
    wake_up_all_sites_concurrent
    
    overall_end=$(date +%s.%3N)
    total_duration=$(echo "$overall_end - $overall_start" | bc -l)
    
    printf "🚀 Deployment complete! Total time: %.2f seconds\n" "$total_duration"
fi

# Clean up temp files
for dir in "${!urls[@]}"; do
    output_file="/tmp/deploy_${dir}.out"
    if [[ -f "$output_file" ]]; then
        rm "$output_file"
    fi
done 