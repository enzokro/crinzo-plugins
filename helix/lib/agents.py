#!/usr/bin/env python3
"""Agent contract loader and validator.

Provides structured validation of agent inputs/outputs against YAML schemas.

Usage:
    from lib.agents import AgentContract

    contract = AgentContract("builder")
    valid, error = contract.validate_input(task_data)
    if not valid:
        raise ValueError(f"Invalid builder input: {error}")

    # After agent completes
    valid, error = contract.validate_output(result)
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try to import yaml, fall back to basic parsing if unavailable
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Try to import jsonschema for validation
try:
    from jsonschema import validate, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


def _parse_yaml_basic(content: str) -> dict:
    """Basic YAML parsing fallback when PyYAML not available.

    Handles simple key: value pairs and lists. Not full YAML spec.
    """
    result = {}
    current_key = None
    current_list = None
    indent_stack = [(0, result)]

    for line in content.split('\n'):
        # Skip comments and empty lines
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(stripped)

        # Handle list items
        if stripped.startswith('- '):
            if current_list is not None:
                item = stripped[2:].strip()
                # Handle simple values
                if ':' not in item or item.startswith('"') or item.startswith("'"):
                    current_list.append(item.strip('"\''))
                else:
                    # Nested object in list - simplified handling
                    parts = item.split(':', 1)
                    current_list.append({parts[0].strip(): parts[1].strip().strip('"\'')})
            continue

        # Handle key: value pairs
        if ':' in stripped:
            parts = stripped.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ''

            # Find the right parent dict based on indent
            while indent_stack and indent <= indent_stack[-1][0] and len(indent_stack) > 1:
                indent_stack.pop()

            parent = indent_stack[-1][1]

            if value:
                # Simple value
                if value.startswith('[') and value.endswith(']'):
                    # Inline list
                    parent[key] = [v.strip().strip('"\'') for v in value[1:-1].split(',') if v.strip()]
                elif value in ('true', 'True'):
                    parent[key] = True
                elif value in ('false', 'False'):
                    parent[key] = False
                elif value.isdigit():
                    parent[key] = int(value)
                elif value.replace('.', '').isdigit():
                    parent[key] = float(value)
                else:
                    parent[key] = value.strip('"\'')
                current_list = None
            else:
                # Start of nested structure or list
                parent[key] = {}
                indent_stack.append((indent + 2, parent[key]))
                # Check if next lines are list items
                current_list = None
                # Peek ahead - simplified, assume list if key suggests it
                if key in ('tools', 'required', 'enum', 'items', 'files', 'questions'):
                    parent[key] = []
                    current_list = parent[key]

    return result


class AgentContract:
    """Loads and validates agent contracts from YAML configs."""

    def __init__(self, name: str):
        """Load agent contract by name.

        Args:
            name: Agent name without prefix (e.g., "builder" not "helix-builder")
        """
        self.name = name
        self.config = self._load_config()
        self.input_schema = self.config.get("input_schema", {})
        self.output_schema = self.config.get("output_schema", {})
        self.tools = self.config.get("tools", [])
        self.model = self.config.get("model", "opus")

    def _load_config(self) -> dict:
        """Load agent config from MD frontmatter or YAML file.

        Tries MD file first (with YAML frontmatter), falls back to .yaml file.
        """
        plugin_root = Path(__file__).parent.parent
        clean_name = self.name.replace("helix-", "")

        # Try MD file first (preferred)
        md_path = plugin_root / "agents" / f"{clean_name}.md"
        if md_path.exists():
            content = md_path.read_text()
            frontmatter = self._extract_frontmatter(content)
            if frontmatter:
                return frontmatter

        # Fall back to YAML file
        yaml_path = plugin_root / "agents" / f"{clean_name}.yaml"
        if not yaml_path.exists():
            yaml_path = plugin_root / "agents" / f"{self.name}.yaml"

        if yaml_path.exists():
            content = yaml_path.read_text()
            if HAS_YAML:
                return yaml.safe_load(content)
            else:
                return _parse_yaml_basic(content)

        raise FileNotFoundError(f"Agent config not found for: {self.name}")

    def _extract_frontmatter(self, content: str) -> Optional[dict]:
        """Extract YAML frontmatter from markdown file.

        Expects format:
        ---
        key: value
        ---
        # Markdown content
        """
        if not content.startswith("---"):
            return None

        # Find closing ---
        end_idx = content.find("\n---", 3)
        if end_idx == -1:
            return None

        frontmatter_text = content[4:end_idx].strip()

        if HAS_YAML:
            return yaml.safe_load(frontmatter_text)
        else:
            return _parse_yaml_basic(frontmatter_text)

    def validate_input(self, input_data: dict) -> Tuple[bool, Optional[str]]:
        """Validate input against schema.

        Returns:
            (is_valid, error_message or None)
        """
        if not self.input_schema:
            return True, None

        if not HAS_JSONSCHEMA:
            # Basic validation without jsonschema
            required = self.input_schema.get("required", [])
            for field in required:
                if field not in input_data:
                    return False, f"Missing required field: {field}"
            return True, None

        try:
            validate(instance=input_data, schema=self.input_schema)
            return True, None
        except ValidationError as e:
            return False, str(e.message)

    def validate_output(self, output_data: dict) -> Tuple[bool, Optional[str]]:
        """Validate output against schema.

        Returns:
            (is_valid, error_message or None)
        """
        if not self.output_schema:
            return True, None

        if not HAS_JSONSCHEMA:
            # Basic validation without jsonschema
            required = self.output_schema.get("required", [])
            for field in required:
                if field not in output_data:
                    return False, f"Missing required field: {field}"
            return True, None

        try:
            validate(instance=output_data, schema=self.output_schema)
            return True, None
        except ValidationError as e:
            return False, str(e.message)

    def get_tools_list(self) -> List[str]:
        """Get list of tools this agent can use."""
        return self.tools

    def get_prompt_template(self) -> str:
        """Generate a prompt template from input schema."""
        props = self.input_schema.get("properties", {})
        lines = []
        for key, spec in props.items():
            desc = spec.get("description", "")
            lines.append(f"{key.upper()}: {{{{ {key} }}}}")
            if desc:
                lines.append(f"  # {desc}")
        return "\n".join(lines)

    def format_input(self, input_data: dict) -> str:
        """Format input data as a prompt string."""
        lines = []
        props = self.input_schema.get("properties", {})

        for key in props:
            if key in input_data:
                value = input_data[key]
                if isinstance(value, (list, dict)):
                    value = json.dumps(value)
                lines.append(f"{key.upper()}: {value}")

        return "\n".join(lines)

    def parse_output(self, raw_output: str) -> Tuple[Optional[dict], Optional[str]]:
        """Parse raw agent output into structured dict.

        Attempts to extract JSON from various output formats.

        Returns:
            (parsed_dict or None, error_message or None)
        """
        # Try direct JSON parse
        try:
            return json.loads(raw_output), None
        except json.JSONDecodeError:
            pass

        # Try to find JSON in output (for explorer/observer with prefix)
        json_patterns = [
            r'EXPLORATION_RESULT:\s*(\{.*\})',
            r'OBSERVATION_RESULT:\s*(\{.*\})',
            r'```json\s*(\{.*?\})\s*```',
            r'(\{[^{}]*"status"[^{}]*\})',
        ]

        for pattern in json_patterns:
            match = re.search(pattern, raw_output, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1)), None
                except json.JSONDecodeError:
                    continue

        # Try to parse structured text output (for builder)
        if "DELIVERED:" in raw_output or "BLOCKED:" in raw_output:
            return self._parse_builder_output(raw_output), None

        return None, "Could not parse output as JSON or structured text"

    def _parse_builder_output(self, output: str) -> dict:
        """Parse builder DELIVERED/BLOCKED output format."""
        result = {
            "status": "unknown",
            "summary": "",
            "tried": "",
            "error": ""
        }

        for line in output.strip().split("\n"):
            if line.startswith("DELIVERED:"):
                result["status"] = "delivered"
                result["summary"] = line.replace("DELIVERED:", "").strip()
            elif line.startswith("BLOCKED:"):
                result["status"] = "blocked"
                result["summary"] = line.replace("BLOCKED:", "").strip()
            elif line.startswith("TRIED:"):
                result["tried"] = line.replace("TRIED:", "").strip()
            elif line.startswith("ERROR:"):
                result["error"] = line.replace("ERROR:", "").strip()

        return result


def get_all_contracts() -> Dict[str, AgentContract]:
    """Load all agent contracts.

    Returns:
        Dict mapping agent name to AgentContract
    """
    contracts = {}
    plugin_root = Path(__file__).parent.parent
    agents_dir = plugin_root / "agents"

    # Collect unique agent names from both .md and .yaml files
    agent_names = set()
    for md_file in agents_dir.glob("*.md"):
        agent_names.add(md_file.stem)
    for yaml_file in agents_dir.glob("*.yaml"):
        agent_names.add(yaml_file.stem)

    for name in agent_names:
        try:
            contracts[name] = AgentContract(name)
        except Exception as e:
            print(f"Warning: Could not load {name}: {e}")

    return contracts


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent contract utilities")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # list command
    subparsers.add_parser("list", help="List all agent contracts")

    # show command
    p = subparsers.add_parser("show", help="Show agent contract details")
    p.add_argument("name", help="Agent name")

    # validate-input command
    p = subparsers.add_parser("validate-input", help="Validate input JSON")
    p.add_argument("name", help="Agent name")
    p.add_argument("input_json", help="Input JSON string")

    # validate-output command
    p = subparsers.add_parser("validate-output", help="Validate output JSON")
    p.add_argument("name", help="Agent name")
    p.add_argument("output_json", help="Output JSON string")

    args = parser.parse_args()

    if args.cmd == "list":
        contracts = get_all_contracts()
        for name, contract in contracts.items():
            print(f"{name}: {contract.config.get('description', 'No description')}")

    elif args.cmd == "show":
        contract = AgentContract(args.name)
        print(json.dumps(contract.config, indent=2, default=str))

    elif args.cmd == "validate-input":
        contract = AgentContract(args.name)
        data = json.loads(args.input_json)
        valid, error = contract.validate_input(data)
        print(json.dumps({"valid": valid, "error": error}))

    elif args.cmd == "validate-output":
        contract = AgentContract(args.name)
        data = json.loads(args.output_json)
        valid, error = contract.validate_output(data)
        print(json.dumps({"valid": valid, "error": error}))
