"""Typer/Click command inventory for agent-guide appendix."""

from __future__ import annotations

def _first_help_line(help_text: str | None) -> str:
    if not help_text:
        return ""
    return help_text.strip().split("\n")[0].strip()


def render_command_appendix() -> str:
    """Compact markdown list of top-level commands and nested subcommands."""
    from typer.main import get_command

    from repograph.cli.main import app

    click_group = get_command(app)
    lines: list[str] = ["## CLI command reference", ""]

    lines.append("Top-level commands (names + one-line help; see `repograph <cmd> --help` for flags):")
    lines.append("")
    for name in sorted(click_group.commands.keys()):
        cmd = click_group.commands[name]
        hint = _first_help_line(cmd.help)
        suffix = f" — {hint}" if hint else ""
        lines.append(f"- **{name}**{suffix}")

    for group in app.registered_groups:
        group_name = group.name or ""
        if not group_name:
            continue
        sub = get_command(group.typer_instance)
        lines.append("")
        lines.append(f"### `repograph {group_name}`")
        lines.append("")
        for sub_name in sorted(sub.commands.keys()):
            sub_cmd = sub.commands[sub_name]
            hint = _first_help_line(sub_cmd.help)
            suffix = f" — {hint}" if hint else ""
            lines.append(f"- **{sub_name}**{suffix}")

    return "\n".join(lines).rstrip()
