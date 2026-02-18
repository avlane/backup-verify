"""Render an Analysis for people (text) or machines (JSON)."""
import json
from dataclasses import asdict


def render_text(analysis):
    counts = analysis.counts()
    lines = [
        "backup-verify report for %s" % (analysis.server or "(unknown server)"),
        "server time: %s" % analysis.now.strftime("%Y-%m-%d %H:%M:%S"),
        "%d database(s) checked: %d ok, %d with warnings, %d critical" % (
            counts["databases"], counts["ok"], counts["warning"], counts["critical"]),
        "",
    ]
    if not analysis.findings:
        lines.append("No problems found.")
    for f in analysis.findings:
        lines.append("[%s] %s: %s - %s" % (f.severity.upper(), f.database, f.code, f.message))
    return "\n".join(lines) + "\n"


def _chain_entry(backup):
    return {
        "backup_set_id": backup.backup_set_id,
        "type": backup.type_name,
        "finished": backup.finish.isoformat(timespec="seconds"),
        "devices": list(backup.devices),
    }


def render_json(analysis):
    doc = {
        "server": analysis.server,
        "server_time": analysis.now.isoformat(timespec="seconds"),
        "summary": analysis.counts(),
        "findings": [asdict(f) for f in analysis.findings],
        "restore_chains": {name: [_chain_entry(b) for b in chain] for name, chain in analysis.chains.items()},
    }
    return json.dumps(doc, indent=2) + "\n"


def _cell(value):
    """Escape text for a Markdown table cell."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(analysis):
    counts = analysis.counts()
    lines = [
        "# Backup verification: %s" % (analysis.server or "(unknown server)"),
        "",
        "Server time %s. %d database(s) checked: %d ok, %d with warnings, %d critical." % (
            analysis.now.strftime("%Y-%m-%d %H:%M:%S"), counts["databases"], counts["ok"],
            counts["warning"], counts["critical"]),
        "",
    ]
    if not analysis.findings:
        lines.append("No problems found.")
    else:
        lines.append("| Severity | Database | Code | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for f in analysis.findings:
            lines.append("| %s | %s | `%s` | %s |" % (f.severity, _cell(f.database), f.code, _cell(f.message)))
    return "\n".join(lines) + "\n"


RENDERERS = {"text": render_text, "json": render_json, "markdown": render_markdown}


def render(analysis, fmt="text"):
    try:
        return RENDERERS[fmt](analysis)
    except KeyError:
        raise ValueError("unknown report format: %s" % fmt) from None
