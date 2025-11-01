#!/bin/bash

# Check if we want to rollback to a specific commit
ROLLBACK_COMMIT=""
FIX_HEAD_MODE=false
FIX_CONFLICTS_MODE=false
CONFLICT_FILES=()
if [ "$1" = "--rollback" ] && [ -n "$2" ]; then
    ROLLBACK_COMMIT="$2"
    echo "🔄 ROLLBACK MODE: Will checkout commit $ROLLBACK_COMMIT"
    echo ""
elif [ "$1" = "--fix-conflicts" ]; then
    FIX_CONFLICTS_MODE=true
    shift
    while [ $# -gt 0 ]; do
        CONFLICT_FILES+=("$1")
        shift
    done
    echo "🔧 FIX CONFLICTS MODE: Will restore --staged and re-add files: ${CONFLICT_FILES[*]}"
    echo ""
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "========================================"
    echo "PULLS.SH - Git Repository Manager"
    echo "========================================"
    echo ""
    echo "Usage:"
    echo "  ./pulls.sh                    # Normal pull and status"
    echo "  ./pulls.sh --rollback <ref>   # Rollback to specific commit"
    echo "  ./pulls.sh --fix-head         # Fix detached HEAD state"
    echo "  ./pulls.sh --fix-conflicts file1 file2 ... # Fix merge conflicts by restore --staged and re-add"
    echo "  ./pulls.sh --help             # Show this help"
    echo ""
    echo "========================================"
    echo "ROLLBACK EXAMPLES"
    echo "========================================"
    echo "Quick rollbacks:"
    echo "  ./pulls.sh --rollback HEAD~1    # Previous commit"
    echo "  ./pulls.sh --rollback HEAD~2    # 2 commits ago"
    echo "  ./pulls.sh --rollback HEAD~3    # 3 commits ago"
    echo ""
    echo "Find commits to rollback to:"
    echo "  git log --oneline -10           # View last 10 commits"
    echo "  git log --oneline --since='1 hour ago'"
    echo "  git log --oneline --author='Your Name'"
    echo ""
    echo "Rollback to specific commit:"
    echo "  ./pulls.sh --rollback abc123def456"
    echo ""
    echo "Fix detached HEAD state:"
    echo "  ./pulls.sh --fix-head           # Return to main branch"
    echo ""
    echo "Fix merge conflicts:"
    echo "  ./pulls.sh --fix-conflicts static/linuxreport.css static/linuxreport.js"
    echo ""
    echo "Return to latest version:"
    echo "  ./pulls.sh"
    echo ""
    exit 0
elif [ "$1" = "--fix-head" ]; then
    echo "========================================"
    echo "FIXING DETACHED HEAD STATE"
    echo "========================================"
    echo "This will attempt to return all repositories to their main branch."
    echo ""
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        FIX_HEAD_MODE=true
    else
        echo "Aborted."
        exit 1
    fi
fi

# Arrays to store status information
declare -a repo_names
declare -a repo_statuses
declare -a repo_details

# Function to pull and show status for a directory
pull_and_status() {
    local dir=$1
    echo "Processing $dir..."
    cd "$dir"
    
    # Check if directory is a git repository
    if [ ! -d ".git" ]; then
        echo "❌ Not a git repository"
        repo_names+=("$dir")
        repo_statuses+=("❌")
        repo_details+=("Not a git repository")
        cd ..
        echo "----------------------------------------"
        return
    fi
    
    # Get current branch
    local current_branch=$(git branch --show-current 2>/dev/null)
    if [ -z "$current_branch" ]; then
        if [ "$FIX_HEAD_MODE" = true ]; then
            echo "🔄 Fixing detached HEAD state..."
        else
            echo "⚠️  Detached HEAD detected - attempting to return to main branch..."
        fi
        
        # Try to checkout main branch (or master if main doesn't exist)
        if git show-ref --verify --quiet refs/remotes/origin/main; then
            echo "Checking out main branch..."
            git checkout main 2>&1
            current_branch="main"
        elif git show-ref --verify --quiet refs/remotes/origin/master; then
            echo "Checking out master branch..."
            git checkout master 2>&1
            current_branch="master"
        else
            echo "❌ Could not find main or master branch"
            repo_names+=("$dir")
            repo_statuses+=("❌")
            repo_details+=("No main/master branch found")
            cd ..
            echo "----------------------------------------"
            return
        fi
        
        if [ $? -ne 0 ]; then
            echo "❌ Failed to checkout main branch"
            repo_names+=("$dir")
            repo_statuses+=("❌")
            repo_details+=("Failed to checkout main branch")
            cd ..
            echo "----------------------------------------"
            return
        fi
        
        echo "✅ Successfully returned to $current_branch branch"
    fi
    
    # Check if there are uncommitted changes
    local has_changes=$(git status --porcelain 2>/dev/null | wc -l)
    
    # Handle rollback mode
    if [ -n "$ROLLBACK_COMMIT" ]; then
        echo "🔄 Rolling back to commit $ROLLBACK_COMMIT..."
        git checkout "$ROLLBACK_COMMIT" 2>&1

        if [ $? -eq 0 ]; then
            echo "✅ Rollback successful"
            status_icon="🔄"
            status_detail="Rolled back to $ROLLBACK_COMMIT"
        else
            echo "❌ Rollback failed"
            repo_names+=("$dir")
            repo_statuses+=("❌")
            repo_details+=("Rollback failed")
            cd ..
            echo "----------------------------------------"
            return
        fi
    # Handle fix conflicts mode
    elif [ "$FIX_CONFLICTS_MODE" = true ]; then
        echo "🔧 Fixing conflicts for files: ${CONFLICT_FILES[*]}..."
        for file in "${CONFLICT_FILES[@]}"; do
            if [ -f "$file" ]; then
                echo "Restoring --staged for $file..."
                git restore --staged "$file" 2>&1
                if [ $? -eq 0 ]; then
                    echo "Re-adding $file..."
                    git add "$file" 2>&1
                    if [ $? -eq 0 ]; then
                        echo "✅ Fixed conflict for $file"
                    else
                        echo "❌ Failed to re-add $file"
                    fi
                else
                    echo "❌ Failed to restore --staged for $file"
                fi
            else
                echo "⚠️  File $file not found"
            fi
        done

        echo "Checking if conflicts are resolved..."
        if git diff --cached --name-only | grep -q .; then
            echo "✅ Conflicts resolved - ready to commit"
            status_icon="🔧"
            status_detail="Conflicts fixed for: ${CONFLICT_FILES[*]}"
        else
            echo "❌ No staged changes found"
            status_icon="❌"
            status_detail="Failed to fix conflicts"
        fi
    else
        # Normal pull with rebase
        echo "Pulling from origin/$current_branch..."
        git pull --rebase --autostash 2>&1
        
        # Check pull result
        if [ $? -eq 0 ]; then
            echo "✅ Pull successful"
        else
            echo "❌ Pull failed - check for conflicts"
            repo_names+=("$dir")
            repo_statuses+=("❌")
            repo_details+=("Pull failed - conflicts")
            cd ..
            echo "----------------------------------------"
            return
        fi
    fi
    
    # Show clean status summary
    echo "Status summary:"
    if [ "$has_changes" -gt 0 ]; then
        echo "⚠️  Has uncommitted changes ($has_changes files)"
    else
        echo "✅ Working directory clean"
    fi
    
    # Check if up to date with remote
    git fetch origin 2>/dev/null
    local behind=$(git rev-list HEAD..origin/$current_branch --count 2>/dev/null)
    local ahead=$(git rev-list origin/$current_branch..HEAD --count 2>/dev/null)
    
    local status_icon="✅"
    local status_detail=""
    
    # Skip status check if in rollback mode
    if [ -z "$ROLLBACK_COMMIT" ]; then
        if [ "$behind" -gt 0 ]; then
            echo "⬇️  Behind origin/$current_branch by $behind commits"
            status_icon="⬇️"
            status_detail="Behind by $behind commits"
        elif [ "$ahead" -gt 0 ]; then
            echo "⬆️  Ahead of origin/$current_branch by $ahead commits"
            status_icon="⬆️"
            status_detail="Ahead by $ahead commits"
        else
            echo "✅ Up to date with origin/$current_branch"
            status_detail="Up to date"
        fi
    fi
    
    # Store status for summary
    repo_names+=("$dir")
    repo_statuses+=("$status_icon")
    repo_details+=("$status_detail")
    
    cd ..
    echo "----------------------------------------"
}

# Function to display summary
show_summary() {
    echo ""
    echo "========================================"
    echo "SUMMARY OF ALL REPOSITORIES"
    echo "========================================"
    
    local total_repos=${#repo_names[@]}
    local success_count=0
    local warning_count=0
    local error_count=0
    
    for i in "${!repo_names[@]}"; do
        local status_icon="${repo_statuses[$i]}"
        local repo_name="${repo_names[$i]}"
        local detail="${repo_details[$i]}"
        
        printf "%-15s %s %s\n" "$repo_name" "$status_icon" "$detail"
        
        case "$status_icon" in
            "✅") ((success_count++)) ;;
            "⚠️"|"⬇️"|"⬆️") ((warning_count++)) ;;
            "❌") ((error_count++)) ;;
        esac
    done

}

# List of directories to process
directories=(
    "LinuxReport2"
    "CovidReport2"
    "aireport"
    "trumpreport"
    "pvreport"
    "spacereport"
    "robotreport"
)

# Process each directory
for dir in "${directories[@]}"; do
    pull_and_status "$dir"
done

# Show summary at the end
show_summary

# Usage instructions
if [ -n "$ROLLBACK_COMMIT" ]; then
    echo ""
    echo "========================================"
    echo "ROLLBACK COMPLETE"
    echo "========================================"
    echo "To return to the latest version later, run:"
    echo "  ./pulls.sh"
    echo ""
    echo "To rollback to a different commit, run:"
    echo "  ./pulls.sh --rollback <commit-hash>"
    echo ""
    echo "========================================"
    echo "USEFUL ROLLBACK COMMANDS"
    echo "========================================"
    echo "View recent commits:"
    echo "  git log --oneline -10"
    echo ""
    echo "Common rollback targets:"
    echo "  ./pulls.sh --rollback HEAD~1    # Previous commit"
    echo "  ./pulls.sh --rollback HEAD~2    # 2 commits ago"
    echo "  ./pulls.sh --rollback HEAD~3    # 3 commits ago"
    echo "  ./pulls.sh --rollback HEAD~5    # 5 commits ago"
    echo ""
    echo "Rollback to specific commit hash:"
    echo "  ./pulls.sh --rollback abc123def456"
    echo ""
    echo "Find commits by date:"
    echo "  git log --oneline --since='2 hours ago'"
    echo "  git log --oneline --since='1 day ago'"
    echo ""
    echo "Find commits by author:"
    echo "  git log --oneline --author='Your Name'"
    echo ""
elif [ "$FIX_CONFLICTS_MODE" = true ]; then
    echo ""
    echo "========================================"
    echo "CONFLICTS FIXED"
    echo "========================================"
    echo "To complete the merge, run:"
    echo "  git commit"
    echo ""
    echo "To abort the merge instead:"
    echo "  git merge --abort"
    echo ""
fi
