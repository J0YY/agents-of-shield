#!/usr/bin/env python3
"""
Simple test script for the recon agent.
Run this to test the agent with the vulnerable app's log file.
The agent uses a custom MCP server to read network traffic.
"""

import os
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from recon_agent import ReconAgent

# Working directory - adjust based on where you run the script from
# The MCP server expects vulnerable-app/attack_log.json in the working directory
WORKING_DIR = Path(__file__).resolve().parents[2]

def main():
    # Check for OpenAI API key
    if "OPENAI_API_KEY" not in os.environ:
        print("⚠️  Warning: OPENAI_API_KEY not set in environment")
        print("   The agent requires OpenAI API key to function")
        print("   Set it with: export OPENAI_API_KEY='your-key-here'")
        print()
        return
    
    print("🔍 Initializing Recon Agent...")
    print("📡 Using custom MCP server to read network traffic...")
    print(f"📁 Working directory: {WORKING_DIR}")
    print(f"📁 Expected log file: {WORKING_DIR / 'vulnerable-app' / 'attack_log.json'}")
    print()
    
    # Check if log file exists
    log_file = WORKING_DIR / "vulnerable-app" / "attack_log.json"
    if not log_file.exists():
        print(f"⚠️  Warning: Log file not found at {log_file}")
        print("   Make sure the vulnerable app is running and logging to vulnerable-app/attack_log.json")
        print("   Start the vulnerable app: cd vulnerable-app && npm start")
        print()
    
    agent = ReconAgent(working_dir=WORKING_DIR)
    
    print("🚀 Starting investigation...")
    print("   (This may take a moment as it starts the MCP server and analyzes logs)")
    print()
    
    try:
        report = agent.investigate(context={"trigger": "test_run"})
        
        print("=" * 60)
        print("RECON REPORT")
        print("=" * 60)
        print()
        
        print(f"Timestamp: {report.get('timestamp', 'N/A')}")
        print(f"Trigger: {report.get('investigation_trigger', 'N/A')}")
        print()
        
        assessment = report.get('attack_assessment', {})
        if assessment:
            print("ATTACK ASSESSMENT:")
            print(f"  Type: {assessment.get('attack_type', 'unknown')}")
            print(f"  Target: {assessment.get('target', 'unknown')}")
            print(f"  Severity: {assessment.get('severity', 'unknown')}")
            print(f"  Confidence: {assessment.get('confidence', 'unknown')}")
            print()
        
        evidence = report.get('evidence', [])
        if evidence:
            print("EVIDENCE:")
            for ev in evidence:
                print(f"  • {ev}")
            print()
        
        intelligence = report.get('intelligence', {})
        if intelligence:
            print("INTELLIGENCE:")
            for key, value in intelligence.items():
                print(f"  {key}: {value}")
            print()
        
        recommendations = report.get('recommendations', [])
        if recommendations:
            print("RECOMMENDATIONS:")
            for rec in recommendations:
                print(f"  • {rec}")
            print()
        
        # If there's raw output, show it
        if 'raw_output' in report:
            print("RAW OUTPUT:")
            print(report['raw_output'])
            print()
        
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error during investigation: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check that vulnerable-app/attack_log.json exists and contains log entries")
        print("2. Verify OPENAI_API_KEY is set correctly")
        print("3. Ensure the agents framework is installed: pip install openai-agents")
        print("4. Make sure the vulnerable app is running and generating logs")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
