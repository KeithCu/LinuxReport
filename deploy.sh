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
    
    # Clear output file
    > "$output_file"
    
    echo "🔄 Starting $dir..." >> "$output_file"
    
    max_attempts=5
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # Make the request
        response=$(curl -s -w "HTTP_STATUS:%{http_code}" "$url")
        http_status=$(echo "$response" | grep "HTTP_STATUS:" | cut -d: -f2)
        response_content=$(echo "$response" | grep -v "HTTP_STATUS:" | sed -n '9p')
        
        # Check if we got a successful response with content
        if [[ -n "$response_content" ]]; then
            title=$(echo "$response_content" | sed 's/<title>//' | sed 's/<\/title>//' | xargs)
            echo "✅ $dir | $http_status | $title" >> "$output_file"
            break
        elif [[ "$http_status" == "000" ]]; then
            echo "❌ $dir | Connection failed" >> "$output_file"
        else
            echo "⚠️ $dir | Empty response" >> "$output_file"
        fi
        
        if [ $attempt -lt $max_attempts ]; then
            attempt=$((attempt + 1))
            sleep 3
        else
            echo "💥 $dir | Failed after $max_attempts attempts" >> "$output_file"
            break
        fi
    done
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

# Step 1: Change ownership for all directories
echo "Step 1: Changing ownership for all directories..."
for dir in "${!urls[@]}"; do
    chown_directory "$dir"
done

# Step 2: Restart web server
echo "Step 2: Restarting web server..."
sudo systemctl restart "$WEB_SERVER_SERVICE"
sleep 0.25

# Step 3: Wake up all sites with curl requests (multithreaded)
echo "Step 3: Waking up all sites..."
echo "=================================================================================="
echo "Site             | Status | Title"
echo "----------------------------------------------------------------------------------"

# Submit all tasks to background
for dir in "${!urls[@]}"; do
    url="${urls[$dir]}"
    wake_up_site "$dir" "$url" &
done

# Monitor progress in real-time
completed=0
total=${#urls[@]}

while [ $completed -lt $total ]; do
    completed=0
    for dir in "${!urls[@]}"; do
        output_file="/tmp/deploy_${dir}.out"
        if [[ -f "$output_file" ]]; then
            # Check if we have a final result (starts with ✅, ❌, or 💥)
            if grep -q "^[✅❌💥]" "$output_file"; then
                completed=$((completed + 1))
                # Display result if we haven't shown it yet
                if ! grep -q "^DISPLAYED:" "$output_file"; then
                    tail -n 1 "$output_file"
                    echo "DISPLAYED:" >> "$output_file"  # Mark as displayed
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

# Clean up temp files
for dir in "${!urls[@]}"; do
    output_file="/tmp/deploy_${dir}.out"
    if [[ -f "$output_file" ]]; then
        rm "$output_file"
    fi
done

echo "----------------------------------------------------------------------------------"
echo "✅ All sites deployed successfully!"
echo "=================================================================================="

echo "Deployment complete!" 