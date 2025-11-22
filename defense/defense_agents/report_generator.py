from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class ReportGenerator:
    """Produces lightweight JSON + HTML incident reports after every event."""

    def __init__(self, report_dir: Path) -> None:
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.timeline: List[Dict] = []

    def consume_event(
        self,
        event: Dict,
        classification: Dict,
        payload_report: Dict,
        honeypot_result: Dict,
    ) -> List[Path]:
        record = {
            "step": event.get("step"),
            "endpoint": event.get("action", {}).get("target_url"),
            "method": event.get("action", {}).get("action_type"),
            "status": event.get("status"),
            "summary": event.get("response_summary"),
            "classification": classification,
            "payload": payload_report,
            "honeypot": honeypot_result,
            "timestamp": event.get("timestamp"),
        }
        self.timeline.append(record)

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        json_path = self.report_dir / f"incident_report_{stamp}.json"
        html_path = self.report_dir / f"incident_report_{stamp}.html"

        json_path.write_text(json.dumps({"events": self.timeline}, indent=2), encoding="utf-8")
        html_path.write_text(self._render_html(record), encoding="utf-8")

        return [json_path, html_path]

    def _render_html(self, latest_record: Dict) -> str:
        rows = "\n".join(
            f"<li><strong>Step {entry['step']}</strong> — {entry['endpoint']} ({entry['classification']['label']})</li>"
            for entry in self.timeline[-10:]
        )
        honeypot = latest_record.get("honeypot", {}).get("honeypot") or "None"
        return f"""
        <html>
          <head>
            <title>Agents of Shield – Incident Report</title>
            <style>
              body {{ font-family: Arial, sans-serif; background:#0b1221; color:#f5f7ff; padding:2rem; }}
              h1 {{ color:#86fffb; }}
              section {{ margin-bottom: 1.5rem; }}
            </style>
          </head>
          <body>
            <h1>Incident Timeline</h1>
            <section>
              <p>Latest classification: <strong>{latest_record['classification']['label']}</strong></p>
              <p>Honeypot status: <strong>{honeypot}</strong></p>
            </section>
            <section>
              <ul>{rows}</ul>
            </section>
          </body>
        </html>
        """

