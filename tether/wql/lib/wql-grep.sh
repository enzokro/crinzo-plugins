#!/bin/bash
# WQL Grep/Find Commands

wql_grep() {
    local pattern=""
    local section=""
    local status_filter=""
    local case_insensitive=false
    local names_only=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --section|-s)
                section="$2"
                shift 2
                ;;
            --status)
                status_filter="$2"
                shift 2
                ;;
            -i)
                case_insensitive=true
                shift
                ;;
            --names-only|-l)
                names_only=true
                shift
                ;;
            *)
                pattern="$1"
                shift
                ;;
        esac
    done
    
    if [[ -z "$pattern" ]]; then
        echo "Usage: wql grep <pattern> [--section <name>] [--status <status>]"
        return 1
    fi
    
    local grep_opts="-n"
    $case_insensitive && grep_opts+="i"
    
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        
        # Apply status filter
        if [[ -n "$status_filter" ]]; then
            local parsed
            eval "$(wql_parse_filename "$(basename "$file")")"
            [[ "$status" != "$status_filter" ]] && continue
        fi
        
        local content
        if [[ -n "$section" ]]; then
            content=$(wql_get_section "$file" "$section" 2>/dev/null)
        else
            content=$(cat "$file")
        fi
        
        if echo "$content" | grep -q $grep_opts "$pattern" 2>/dev/null; then
            if $names_only; then
                basename "$file"
            else
                echo "=== $(basename "$file") ==="
                if [[ -n "$section" ]]; then
                    echo "[$section]"
                fi
                echo "$content" | grep --color=always $grep_opts "$pattern" 2>/dev/null
                echo ""
            fi
        fi
    done < <(wql_list_files)
}

wql_find() {
    local status_filter=""
    local depth_filter=""
    local min_depth=""
    local slug_contains=""
    local names_only=false
    local path_no_arrows=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --status)
                status_filter="$2"
                shift 2
                ;;
            --depth)
                depth_filter="$2"
                shift 2
                ;;
            --min-depth)
                min_depth="$2"
                shift 2
                ;;
            --slug-contains)
                slug_contains="$2"
                shift 2
                ;;
            --names-only|-l)
                names_only=true
                shift
                ;;
            --path-no-arrows)
                path_no_arrows=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    wql_build_index
    
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        
        local seq="" slug="" status="" parent=""
        eval "$(wql_parse_filename "$(basename "$file")")"
        
        # Status filter
        if [[ -n "$status_filter" && "$status" != "$status_filter" ]]; then
            continue
        fi
        
        # Depth filter
        if [[ -n "$depth_filter" || -n "$min_depth" ]]; then
            local file_depth=$(wql_get_depth "$seq")
            if [[ -n "$depth_filter" && "$file_depth" != "$depth_filter" ]]; then
                continue
            fi
            if [[ -n "$min_depth" && "$file_depth" -le "$min_depth" ]]; then
                continue
            fi
        fi
        
        # Slug filter
        if [[ -n "$slug_contains" && ! "$slug" =~ $slug_contains ]]; then
            continue
        fi
        
        # Path arrows check
        if $path_no_arrows; then
            local path_line=$(wql_get_section "$file" "path" 2>/dev/null)
            if [[ "$path_line" =~ "->" ]]; then
                continue
            fi
        fi
        
        if $names_only; then
            basename "$file"
        else
            echo "$(basename "$file")"
            echo "  Status: $status"
            [[ -n "$parent" ]] && echo "  Parent: $parent"
            echo "  Depth: $(wql_get_depth "$seq")"
            echo ""
        fi
    done < <(wql_list_files)
}

wql_graph() {
    local root=""
    local format="tree"
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --format)
                format="$2"
                shift 2
                ;;
            --dot)
                format="dot"
                shift
                ;;
            --tree)
                format="tree"
                shift
                ;;
            *)
                root="$1"
                shift
                ;;
        esac
    done
    
    wql_build_index
    
    case "$format" in
        dot)
            _graph_dot "$root"
            ;;
        tree)
            _graph_tree "$root"
            ;;
    esac
}

_graph_tree() {
    local root="$1"
    
    if [[ -n "$root" ]]; then
        # Extract sequence if filename given
        if [[ $root =~ ^([0-9]{3}) ]]; then
            root="${BASH_REMATCH[1]}"
        fi
        _print_tree "$root" 0
    else
        # Show all roots
        for seq in "${!WQL_FILES[@]}"; do
            if [[ -z "${WQL_PARENTS[$seq]:-}" ]]; then
                _print_tree "$seq" 0
                echo ""
            fi
        done
    fi
}

_graph_dot() {
    local root="$1"
    
    echo "digraph workspace {"
    echo "  rankdir=TB;"
    echo "  node [shape=box, style=rounded];"
    echo ""
    
    for seq in "${!WQL_FILES[@]}"; do
        local file="${WQL_FILES[$seq]}"
        local basename="${file##*/}"
        local status=""
        eval "$(wql_parse_filename "$basename")"
        
        local color="white"
        case "$status" in
            complete) color="lightgreen" ;;
            blocked) color="lightyellow" ;;
            active) color="lightblue" ;;
        esac
        
        echo "  \"$seq\" [label=\"$seq\\n$slug\", fillcolor=$color, style=filled];"
    done
    
    echo ""
    
    for seq in "${!WQL_FILES[@]}"; do
        local parent="${WQL_PARENTS[$seq]:-}"
        if [[ -n "$parent" ]]; then
            echo "  \"$parent\" -> \"$seq\";"
        fi
    done
    
    echo "}"
}
