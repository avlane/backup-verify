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


def render_json(analysis):
    doc = {
        "server": analysis.server,
        "server_time": analysis.now.isoformat(timespec="seconds"),
        "summary": analysis.counts(),
        "findings": [asdict(f) for f in analysis.findings],
    }
    return json.dumps(doc, indent=2) + "\n"


RENDERERS = {"text": render_text, "json": render_json}


def render(analysis, fmt="text"):
    try:
        return RENDERERS[fmt](analysis)
    except KeyError:
        raise ValueError("unknown report format: %s" % fmt) from None
