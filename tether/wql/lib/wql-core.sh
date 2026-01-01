#!/bin/bash
# WQL Core Functions

# Parse workspace filename into components
# Returns: seq, slug, status, parent (if exists)
wql_parse_filename() {
    local filename="$1"
    local basename="${filename##*/}"
    basename="${basename%.md}"
    
    # Pattern: NNN_slug_status[_from-NNN]
    if [[ $basename =~ ^([0-9]{3})_(.+)_([^_]+)(_from-([0-9]{3}))?$ ]]; then
        echo "seq=${BASH_REMATCH[1]}"
        echo "slug=${BASH_REMATCH[2]}"
        echo "status=${BASH_REMATCH[3]}"
        echo "parent=${BASH_REMATCH[5]:-}"
    # Pattern: YYYYMMDD_slug_status (legacy)
    elif [[ $basename =~ ^([0-9]{8})_(.+)_([^_]+)$ ]]; then
        echo "seq=${BASH_REMATCH[1]}"
        echo "slug=${BASH_REMATCH[2]}"
        echo "status=${BASH_REMATCH[3]}"
        echo "parent="
        echo "format=date"
    else
        echo "seq="
        echo "slug="
        echo "status="
        echo "parent="
        echo "error=parse_failed"
    fi
}

# Get all workspace files
wql_list_files() {
    local ws="${WORKSPACE:-./workspace}"
    find "$ws" -maxdepth 1 -name "*.md" -type f 2>/dev/null | sort
}

# Get section content from a workspace file
# Usage: wql_get_section <file> <section_name>
wql_get_section() {
    local file="$1"
    local section="$2"
    
    case "$section" in
        anchor)
            sed -n '/^## Anchor/,/^## /p' "$file" | head -n -1
            ;;
        path)
            grep -E "^Path:" "$file" | head -1 | sed 's/^Path: *//'
            ;;
        delta)
            grep -E "^Delta:" "$file" | head -1 | sed 's/^Delta: *//'
            ;;
        traces|thinking)
            sed -n '/^## Thinking Traces/,/^## /p' "$file" | head -n -1
            ;;
        delivered)
            sed -n '/^## Delivered/,/^## /p' "$file" | head -n -1
            ;;
        blocked)
            sed -n '/^## Blocked/,/^## /p' "$file" | head -n -1
            ;;
        findings)
            sed -n '/^## Key Findings/,/^## /p' "$file" | head -n -1
            ;;
        *)
            echo "Unknown section: $section" >&2
            return 1
            ;;
    esac
}

# Build associative arrays for lineage
declare -A WQL_FILES      # seq -> filename
declare -A WQL_PARENTS    # seq -> parent_seq
declare -A WQL_CHILDREN   # seq -> space-separated child seqs

wql_build_index() {
    local ws="${WORKSPACE:-./workspace}"
    WQL_FILES=()
    WQL_PARENTS=()
    WQL_CHILDREN=()
    
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        local basename="${file##*/}"
        
        # Parse the filename
        local seq="" slug="" status="" parent=""
        eval "$(wql_parse_filename "$basename")"
        
        [[ -z "$seq" ]] && continue
        
        WQL_FILES["$seq"]="$file"
        
        if [[ -n "$parent" ]]; then
            WQL_PARENTS["$seq"]="$parent"
            WQL_CHILDREN["$parent"]+="$seq "
        fi
    done < <(wql_list_files)
}

# Get ancestors of a sequence (returns space-separated list, oldest first)
wql_get_ancestors() {
    local seq="$1"
    local chain=""
    local current="$seq"
    
    while [[ -n "$current" ]]; do
        chain="$current $chain"
        current="${WQL_PARENTS[$current]:-}"
    done
    
    echo "$chain" | xargs
}

# Get descendants of a sequence (breadth-first)
wql_get_descendants() {
    local seq="$1"
    local result=""
    local queue="$seq"
    
    while [[ -n "$queue" ]]; do
        local current="${queue%% *}"
        queue="${queue#* }"
        [[ "$queue" == "$current" ]] && queue=""
        
        local children="${WQL_CHILDREN[$current]:-}"
        for child in $children; do
            result+="$child "
            queue+="$child "
        done
    done
    
    echo "$result" | xargs
}

# Calculate depth of a file (number of ancestors)
wql_get_depth() {
    local seq="$1"
    local depth=1
    local current="${WQL_PARENTS[$seq]:-}"
    
    while [[ -n "$current" ]]; do
        ((depth++))
        current="${WQL_PARENTS[$current]:-}"
    done
    
    echo "$depth"
}
