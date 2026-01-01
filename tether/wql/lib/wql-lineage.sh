#!/bin/bash
# WQL Lineage Commands

wql_lineage() {
    local selector=""
    local direction="up"
    local min_depth=""
    local show_orphans=false
    local show_longest=false
    local show_roots=false
    local show_leaves=false
    local output_json=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --up|-u)
                direction="up"
                shift
                ;;
            --down|-d)
                direction="down"
                shift
                ;;
            --both|-b)
                direction="both"
                shift
                ;;
            --min-depth)
                min_depth="$2"
                shift 2
                ;;
            --orphans)
                show_orphans=true
                shift
                ;;
            --longest)
                show_longest=true
                shift
                ;;
            --roots)
                show_roots=true
                shift
                ;;
            --leaves)
                show_leaves=true
                shift
                ;;
            --json)
                output_json=true
                shift
                ;;
            *)
                selector="$1"
                shift
                ;;
        esac
    done
    
    wql_build_index
    
    # Handle special queries
    if $show_orphans; then
        _lineage_orphans
        return
    fi
    
    if $show_longest; then
        _lineage_longest
        return
    fi
    
    if $show_roots; then
        _lineage_roots
        return
    fi
    
    if $show_leaves; then
        _lineage_leaves
        return
    fi
    
    if [[ -n "$min_depth" ]]; then
        _lineage_min_depth "$min_depth"
        return
    fi
    
    # Specific file lineage
    if [[ -n "$selector" ]]; then
        # Extract sequence number if full filename given
        if [[ $selector =~ ^([0-9]{3}) ]]; then
            selector="${BASH_REMATCH[1]}"
        fi
        
        case "$direction" in
            up)
                _lineage_ancestors "$selector"
                ;;
            down)
                _lineage_descendants "$selector"
                ;;
            both)
                _lineage_full "$selector"
                ;;
        esac
    else
        # Show all chains
        _lineage_all
    fi
}

_lineage_ancestors() {
    local seq="$1"
    local chain=$(wql_get_ancestors "$seq")
    local depth=$(echo "$chain" | wc -w | tr -d ' ')
    
    echo "Chain: $(echo $chain | tr ' ' ' -> ') (depth: $depth)"
    for s in $chain; do
        local file="${WQL_FILES[$s]}"
        [[ -n "$file" ]] && echo "  $(basename "$file")"
    done
}

_lineage_descendants() {
    local seq="$1"
    local descendants=$(wql_get_descendants "$seq")
    
    echo "Descendants of $seq:"
    echo "  $(basename "${WQL_FILES[$seq]}")"
    for s in $descendants; do
        local depth=$(wql_get_depth "$s")
        local indent=$(printf '%*s' $((depth * 2)) '')
        echo "$indent$(basename "${WQL_FILES[$s]}")"
    done
}

_lineage_full() {
    local seq="$1"
    echo "=== Ancestors ==="
    _lineage_ancestors "$seq"
    echo ""
    echo "=== Descendants ==="
    _lineage_descendants "$seq"
}

_lineage_longest() {
    local longest_chain=""
    local max_depth=0
    
    for seq in "${!WQL_FILES[@]}"; do
        local chain=$(wql_get_ancestors "$seq")
        local depth=$(echo "$chain" | wc -w | tr -d ' ')
        if [[ $depth -gt $max_depth ]]; then
            max_depth=$depth
            longest_chain="$chain"
        fi
    done
    
    echo "Longest chain (depth: $max_depth):"
    echo "  $(echo $longest_chain | tr ' ' ' -> ')"
    echo ""
    for s in $longest_chain; do
        echo "  $(basename "${WQL_FILES[$s]}")"
    done
}

_lineage_min_depth() {
    local min="$1"
    echo "Chains with depth > $((min)):"
    echo ""
    
    for seq in "${!WQL_FILES[@]}"; do
        local depth=$(wql_get_depth "$seq")
        if [[ $depth -gt $min ]]; then
            local chain=$(wql_get_ancestors "$seq")
            echo "Chain (depth: $depth): $(echo $chain | tr ' ' ' -> ')"
        fi
    done
}

_lineage_orphans() {
    echo "Orphans (parent reference not found):"
    local found=false
    
    for seq in "${!WQL_FILES[@]}"; do
        local parent="${WQL_PARENTS[$seq]:-}"
        if [[ -n "$parent" && -z "${WQL_FILES[$parent]:-}" ]]; then
            echo "  $(basename "${WQL_FILES[$seq]}") -> missing parent: $parent"
            found=true
        fi
    done
    
    $found || echo "  (none)"
}

_lineage_roots() {
    echo "Root files (no parent):"
    for seq in "${!WQL_FILES[@]}"; do
        if [[ -z "${WQL_PARENTS[$seq]:-}" ]]; then
            echo "  $(basename "${WQL_FILES[$seq]}")"
        fi
    done
}

_lineage_leaves() {
    echo "Leaf files (no children):"
    for seq in "${!WQL_FILES[@]}"; do
        if [[ -z "${WQL_CHILDREN[$seq]:-}" ]]; then
            echo "  $(basename "${WQL_FILES[$seq]}")"
        fi
    done
}

_lineage_all() {
    echo "All lineage chains:"
    echo ""
    
    # Find all roots first
    local roots=""
    for seq in "${!WQL_FILES[@]}"; do
        if [[ -z "${WQL_PARENTS[$seq]:-}" ]]; then
            roots+="$seq "
        fi
    done
    
    for root in $roots; do
        _print_tree "$root" 0
        echo ""
    done
}

_print_tree() {
    local seq="$1"
    local level="$2"
    local indent=$(printf '%*s' $((level * 2)) '')
    
    echo "${indent}$(basename "${WQL_FILES[$seq]}")"
    
    local children="${WQL_CHILDREN[$seq]:-}"
    for child in $children; do
        _print_tree "$child" $((level + 1))
    done
}
