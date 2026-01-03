#!/usr/bin/env python3
"""Semantic concept expansion for lattice queries.

Enables finding related decisions when query terms don't match exactly.
"auth" -> finds decisions about "session", "token", "credential", etc.
"""

# Core concept clusters - expand as domains emerge
CONCEPT_MAP = {
    # Authentication & Identity
    "auth": ["authentication", "session", "login", "credential", "token", "identity", "oauth", "jwt", "password"],
    "session": ["auth", "token", "cookie", "state", "user", "login"],
    "token": ["auth", "session", "jwt", "refresh", "access", "bearer"],

    # Error Handling
    "error": ["exception", "failure", "catch", "handle", "retry", "fallback", "recover"],
    "retry": ["error", "backoff", "resilience", "failure", "timeout"],

    # Data & Persistence
    "data": ["model", "schema", "entity", "record", "store", "persist", "database"],
    "model": ["data", "schema", "entity", "type", "struct", "class"],
    "database": ["data", "persist", "query", "store", "sql", "orm"],

    # API & Networking
    "api": ["endpoint", "route", "handler", "request", "response", "rest", "http"],
    "endpoint": ["api", "route", "handler", "controller", "path"],
    "request": ["api", "response", "http", "fetch", "client"],

    # Security
    "security": ["auth", "permission", "role", "access", "encrypt", "hash", "validate"],
    "permission": ["security", "role", "access", "authorize", "guard"],
    "encrypt": ["security", "hash", "crypto", "secret", "key"],

    # Performance
    "performance": ["cache", "optimize", "latency", "throughput", "batch", "async"],
    "cache": ["performance", "store", "invalidate", "ttl", "memory"],
    "async": ["performance", "concurrent", "parallel", "await", "promise"],

    # Testing
    "test": ["spec", "assert", "mock", "fixture", "coverage", "unit", "integration"],
    "mock": ["test", "stub", "fake", "spy", "fixture"],

    # Configuration
    "config": ["setting", "environment", "option", "parameter", "env"],
    "environment": ["config", "env", "variable", "secret", "deploy"],

    # Validation
    "validate": ["check", "verify", "sanitize", "parse", "constraint", "rule"],
    "sanitize": ["validate", "clean", "escape", "input", "security"],

    # State Management
    "state": ["store", "reducer", "action", "context", "global"],
    "store": ["state", "persist", "cache", "data", "memory"],
}


def expand_query(term: str) -> list:
    """Expand a query term to related concepts.

    Args:
        term: The search term to expand

    Returns:
        List of related terms including the original
    """
    term_lower = term.lower().strip()
    if not term_lower:
        return []

    expanded = {term_lower}

    # Direct lookup
    if term_lower in CONCEPT_MAP:
        expanded.update(CONCEPT_MAP[term_lower])

    # Reverse lookup - find clusters that contain this term
    for cluster, concepts in CONCEPT_MAP.items():
        if term_lower in concepts:
            expanded.add(cluster)
            expanded.update(concepts)

    return list(expanded)


def get_concept_cluster(term: str) -> str:
    """Get the primary cluster for a term.

    Args:
        term: The term to classify

    Returns:
        The cluster name, or the term itself if not found
    """
    term_lower = term.lower().strip()

    # Direct match
    if term_lower in CONCEPT_MAP:
        return term_lower

    # Find containing cluster
    for cluster, concepts in CONCEPT_MAP.items():
        if term_lower in concepts:
            return cluster

    return term_lower


def expand_multiple(terms: list) -> list:
    """Expand multiple query terms.

    Args:
        terms: List of search terms

    Returns:
        Deduplicated list of all expanded terms
    """
    expanded = set()
    for term in terms:
        expanded.update(expand_query(term))
    return list(expanded)


# --- CLI for testing ---

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python concepts.py <term> [term2 ...]")
        print("\nExample:")
        print("  python concepts.py auth")
        print("  python concepts.py session token")
        return

    terms = sys.argv[1:]

    if len(terms) == 1:
        expanded = expand_query(terms[0])
        cluster = get_concept_cluster(terms[0])
        print(f"Term: {terms[0]}")
        print(f"Cluster: {cluster}")
        print(f"Expanded: {', '.join(sorted(expanded))}")
    else:
        expanded = expand_multiple(terms)
        print(f"Terms: {', '.join(terms)}")
        print(f"Expanded: {', '.join(sorted(expanded))}")


if __name__ == "__main__":
    main()
