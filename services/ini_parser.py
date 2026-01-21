# services/ini_parser.py
"""
INI-style permission configuration parser.

Handles parsing and generating INI-format text for role permissions.
Example format:
    [Player]
    alderonid=true
    playerid=false
"""

from config.commands import COMMAND_CATEGORIES, get_all_commands


class INIParseError(Exception):
    """Raised when INI parsing fails."""
    pass


def parse_permissions_ini(text: str) -> dict:
    """
    Parse INI-style permission text into {command: bool} dict.

    Accepts values: true, false, 1, 0, yes, no, on, off
    Lines starting with # or ; are comments.
    Empty lines and section headers are ignored for values.

    Args:
        text: The INI-format text to parse

    Returns:
        Dict mapping command names to boolean values

    Raises:
        INIParseError: If text contains invalid syntax
    """
    permissions = {}
    current_section = None
    line_number = 0

    for line in text.strip().split('\n'):
        line_number += 1
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#') or line.startswith(';'):
            continue

        # Section header
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            continue

        # Key=value pair
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip().lower()

            # Parse boolean value
            if value in ('true', '1', 'yes', 'on'):
                permissions[key] = True
            elif value in ('false', '0', 'no', 'off'):
                permissions[key] = False
            else:
                raise INIParseError(
                    f"Line {line_number}: Invalid value '{value}' for '{key}'. "
                    f"Use true/false."
                )
        else:
            # Line has content but no = sign
            raise INIParseError(
                f"Line {line_number}: Invalid syntax '{line}'. "
                f"Expected 'command=true' or 'command=false'."
            )

    return permissions


def generate_permissions_ini(permissions: dict) -> str:
    """
    Generate INI text from permissions dict.

    Commands are organized by category with section headers.
    Missing commands default to false.

    Args:
        permissions: Dict mapping command names to boolean values

    Returns:
        Formatted INI text string
    """
    lines = []

    for category, commands in COMMAND_CATEGORIES.items():
        lines.append(f'[{category}]')
        for cmd in commands:
            value = 'true' if permissions.get(cmd, False) else 'false'
            lines.append(f'{cmd}={value}')
        lines.append('')  # Blank line between sections

    # Remove trailing blank line
    if lines and lines[-1] == '':
        lines.pop()

    return '\n'.join(lines)


def validate_permissions(permissions: dict) -> tuple[bool, list[str]]:
    """
    Validate a permissions dict.

    Args:
        permissions: Dict of command -> bool

    Returns:
        (is_valid, list of error messages)
    """
    errors = []
    all_commands = set(get_all_commands())

    for cmd in permissions:
        if cmd not in all_commands:
            errors.append(f"Unknown command: '{cmd}'")

    return len(errors) == 0, errors


def get_permissions_diff(old: dict, new: dict) -> dict:
    """
    Compare two permission dicts and return changes.

    Returns:
        Dict with 'added', 'removed', 'changed' keys
    """
    all_commands = set(get_all_commands())

    added = []      # Commands newly enabled
    removed = []    # Commands newly disabled
    changed = []    # Commands that changed

    for cmd in all_commands:
        old_val = old.get(cmd, False)
        new_val = new.get(cmd, False)

        if old_val != new_val:
            changed.append(cmd)
            if new_val:
                added.append(cmd)
            else:
                removed.append(cmd)

    return {
        'added': added,
        'removed': removed,
        'changed': changed,
        'total_enabled': sum(1 for v in new.values() if v)
    }
