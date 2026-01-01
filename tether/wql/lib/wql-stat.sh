#!/bin/bash
# WQL Statistics Commands

wql_stat() {
    local stat_type=""
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            status|depth|sequence|blockers)
                stat_type="$1"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    wql_build_index
    
    case "$stat_type" in
        status)
            _stat_status
            ;;
        depth)
            _stat_depth
            ;;
        sequence)
            _stat_sequence
            ;;
        blockers)
            _stat_blockers
            ;;
        *)
            _stat_full
            ;;
    esac
}

_stat_full() {
    local total=0
    local complete=0
    local active=0
    local blocked=0
    local max_depth=0
    local orphans=0
    local roots=0
    local traces_words=0
    
    for seq in "${!WQL_FILES[@]}"; do
        ((total++))
        
        local file="${WQL_FILES[$seq]}"
        local status=""
        eval "$(wql_parse_filename "$(basename "$file")")"
        
        case "$status" in
            complete) ((complete++)) ;;
            active) ((active++)) ;;
            blocked) ((blocked++)) ;;
        esac
        
        local depth=$(wql_get_depth "$seq")
        [[ $depth -gt $max_depth ]] && max_depth=$depth
        
        local parent="${WQL_PARENTS[$seq]:-}"
        if [[ -n "$parent" && -z "${WQL_FILES[$parent]:-}" ]]; then
            ((orphans++))
        fi
        
        if [[ -z "$parent" ]]; then
            ((roots++))
        fi
        
        # Count words in Thinking Traces
        local traces=$(wql_get_section "$file" "traces" 2>/dev/null)
        local wc=$(echo "$traces" | wc -w | tr -d ' ')
        traces_words=$((traces_words + wc))
    done
    
    local avg_traces=0
    [[ $total -gt 0 ]] && avg_traces=$((traces_words / total))
    
    echo "Workspace Statistics"
    echo "===================="
    echo ""
    echo "Total files:     $total"
    echo ""
    echo "By status:"
    echo "  complete:      $complete"
    echo "  active:        $active"
    echo "  blocked:       $blocked"
    echo ""
    echo "Lineage:"
    echo "  Max depth:     $max_depth"
    echo "  Root files:    $roots"
    echo "  Orphans:       $orphans"
    echo ""
    echo "Content:"
    echo "  Avg traces:    $avg_traces words"
}

_stat_status() {
    echo "Status Distribution"
    echo "==================="
    
    declare -A counts
    for seq in "${!WQL_FILES[@]}"; do
        local file="${WQL_FILES[$seq]}"
        local status=""
        eval "$(wql_parse_filename "$(basename "$file")")"
        counts[$status]=$((${counts[$status]:-0} + 1))
    done
    
    for status in "${!counts[@]}"; do
        printf "  %-12s %d\n" "$status:" "${counts[$status]}"
    done
}

_stat_depth() {
    echo "Depth Distribution"
    echo "=================="
    
    declare -A depths
    for seq in "${!WQL_FILES[@]}"; do
        local depth=$(wql_get_depth "$seq")
        depths[$depth]=$((${depths[$depth]:-0} + 1))
    done
    
    for d in $(echo "${!depths[@]}" | tr ' ' '\n' | sort -n); do
        printf "  Depth %d:  %d files\n" "$d" "${depths[$d]}"
    done
}

_stat_sequence() {
    echo "Sequence Distribution"
    echo "====================="
    
    declare -A seqs
    for seq in "${!WQL_FILES[@]}"; do
        seqs[$seq]=$((${seqs[$seq]:-0} + 1))
    done
    
    for s in $(echo "${!seqs[@]}" | tr ' ' '\n' | sort); do
        local file="${WQL_FILES[$s]}"
        local slug=""
        eval "$(wql_parse_filename "$(basename "$file")")"
        printf "  %s: %s\n" "$s" "$slug"
    done
}

_stat_blockers() {
    echo "Blocker Analysis"
    echo "================"
    echo ""
    
    local found=false
    for seq in "${!WQL_FILES[@]}"; do
        local file="${WQL_FILES[$seq]}"
        local status=""
        eval "$(wql_parse_filename "$(basename "$file")")"
        
        if [[ "$status" == "blocked" ]]; then
            found=true
            echo "$(basename "$file"):"
            local blocked_content=$(wql_get_section "$file" "blocked" 2>/dev/null)
            if [[ -n "$blocked_content" ]]; then
                echo "$blocked_content" | head -10 | sed 's/^/  /'
            else
                echo "  (no blocked section found)"
            fi
            echo ""
        fi
    done
    
    $found || echo "No blocked files found."
}
