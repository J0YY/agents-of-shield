from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from defense_agents.attack_classifier import AttackClassifier
from defense_agents.defense_memory import DefenseMemoryAgent
from defense_agents.honeypot_manager import HoneypotManager
from defense_agents.network_monitor import NetworkMonitor
from defense_agents.payload_analysis import PayloadAnalysisAgent
from defense_agents.report_generator import ReportGenerator


class EventRouter:
    """Routes attacker events through the defensive pipeline."""

    def __init__(self, state_dir: Path, report_dir: Path) -> None:
        self.state_dir = state_dir
        self.report_dir = report_dir
        self.honeypot_manager = HoneypotManager(state_dir)
        self.network_monitor = NetworkMonitor(state_dir)
        self.payload_analysis = PayloadAnalysisAgent()
        self.attack_classifier = AttackClassifier()
        self.defense_memory = DefenseMemoryAgent(state_dir)
        self.report_generator = ReportGenerator(report_dir)

    def route(self, event: Dict) -> Dict:
        """Run the event through all defensive agents and aggregate the outputs."""

        timestamp = event.get("timestamp") or datetime.utcnow().isoformat()
        event["timestamp"] = timestamp

        network_record = self.network_monitor.record(event)
        payload_report = self.payload_analysis.analyze(event)
        honeypot_result = self.honeypot_manager.inspect(event)
        classification = self.attack_classifier.classify(event, payload_report)
        defense_memory_state = self.defense_memory.update(event, payload_report, classification, honeypot_result)
        report_paths = self.report_generator.consume_event(
            event,
            classification=classification,
            payload_report=payload_report,
            honeypot_result=honeypot_result,
        )

        return {
            "type": "ATTACK_EVENT",
            "event": event,
            "network": network_record,
            "payload": payload_report,
            "classification": classification,
            "honeypot": honeypot_result,
            "defense_memory": defense_memory_state,
            "reports": [str(path) for path in report_paths],
        }

