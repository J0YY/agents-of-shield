#!/usr/bin/env python3
"""
Simple test script for the PCAP recon agent.
Run this to test the agent with a captured PCAP file.
The agent uses a custom MCP server to analyze network traffic.
"""

import os
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from recon_agent_pcap import ReconAgentPcap

# Working directory - adjust based on where you run the script from
# The MCP server expects traffic.pcap in the working directory
WORKING_DIR = Path(__file__).resolve().parents[2]


def main():
    # Check for OpenAI API key
    if "OPENAI_API_KEY" not in os.environ:
        print("⚠️  Warning: OPENAI_API_KEY not set in environment")
        print("   The agent requires OpenAI API key to function")
        print("   Set it with: export OPENAI_API_KEY='your-key-here'")
        print()
        return

    print("🔍 Initializing PCAP Recon Agent...")
    print("📡 Using custom MCP server to analyze network traffic...")
    print(f"📁 Working directory: {WORKING_DIR}")
    print(f"📁 Expected PCAP file: {WORKING_DIR / 'traffic.pcap'}")
    print()

    # Check if PCAP file exists
    pcap_file = WORKING_DIR / "traffic.pcap"
    if not pcap_file.exists():
        print(f"⚠️  Warning: PCAP file not found at {pcap_file}")
        print("   You need to capture network traffic first.")
        print()
        print("   To capture traffic:")
        print("   macOS: sudo tshark -i lo0 -w traffic.pcap")
        print("   Linux: sudo tshark -i lo -w traffic.pcap")
        print()
        print("   Then generate some suspicious activity (port scans, HTTP enumeration)")
        print("   and press Ctrl+C to stop the capture.")
        print()
        return

    agent = ReconAgentPcap(working_dir=WORKING_DIR)

    print("🚀 Starting investigation...")
    print("   (This may take a moment as it starts the MCP server and analyzes PCAP)")
    print()

    try:
        result = agent.investigate(context={"trigger": "manual_test"})

        print("=" * 70)
        print("INVESTIGATION COMPLETE")
        print("=" * 70)
        print()

        # Print attack assessment
        if "attack_assessment" in result:
            assessment = result["attack_assessment"]
            print("🎯 Attack Assessment:")
            print(f"   Type: {assessment.get('attack_type', 'unknown')}")
            print(f"   Target: {assessment.get('target', 'unknown')}")
            print(f"   Severity: {assessment.get('severity', 'unknown').upper()}")
            print(f"   Confidence: {assessment.get('confidence', 'unknown')}")
            print()

        # Print evidence
        if "evidence" in result and result["evidence"]:
            print("📋 Evidence Found:")
            for i, evidence in enumerate(result["evidence"], 1):
                print(f"   {i}. {evidence}")
            print()

        # Print recommendations
        if "recommendations" in result and result["recommendations"]:
            print("💡 Recommendations:")
            for i, rec in enumerate(result["recommendations"], 1):
                print(f"   {i}. {rec}")
            print()

        # Print intelligence
        if "intelligence" in result:
            print("📊 Intelligence Summary:")
            intel = result["intelligence"]
            for key, value in intel.items():
                print(f"   {key}: {value}")
            print()

        # Print metadata
        print("ℹ️  Metadata:")
        print(f"   Timestamp: {result.get('timestamp', 'N/A')}")
        print(f"   Trigger: {result.get('investigation_trigger', 'N/A')}")
        print(f"   PCAP File: {result.get('pcap_file', 'N/A')}")
        print()

        # Show raw output if present (debugging)
        if "raw_output" in result and result.get("attack_assessment", {}).get("attack_type") == "unknown":
            print("⚠️  Raw Output (for debugging):")
            print(result["raw_output"][:500])
            print()

        print("=" * 70)

    except Exception as e:
        print(f"❌ Error during investigation: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
