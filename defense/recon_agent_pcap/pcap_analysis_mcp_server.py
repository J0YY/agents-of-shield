# pcap_analysis_mcp_server.py
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "PcapAnalysisServer",
    json_response=True,
)


def run_tshark_command(
    pcap_path: Path,
    display_filter: str = "",
    fields: Optional[List[str]] = None,
    limit: int = 1000
) -> List[Dict]:
    """Run tshark command and return parsed results."""
    if not pcap_path.exists():
        raise FileNotFoundError(f"PCAP file not found: {pcap_path}")

    cmd = ["tshark", "-r", str(pcap_path), "-T", "json"]

    if display_filter:
        cmd.extend(["-Y", display_filter])

    if fields:
        for field in fields:
            cmd.extend(["-e", field])
        cmd.append("-Ejson.format=plain")

    cmd.extend(["-c", str(limit)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

        if result.stdout.strip():
            return json.loads(result.stdout)
        return []

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"tshark command failed: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("tshark command timed out after 30 seconds")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse tshark JSON output: {e}")


@mcp.tool()
def read_pcap_summary(
    pcap_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    max_packets: int = 100
) -> Dict:
    """
    Read a PCAP file and return a summary of network traffic.

    Args:
        pcap_file: Path to the .pcap file. If not provided, uses traffic.pcap in working directory.
        working_dir: Working directory. If not provided, uses current directory.
        max_packets: Maximum number of packets to analyze (default: 100)

    Returns:
        Dictionary with summary statistics and sample packets
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if pcap_file:
        # If pcap_file is absolute, use it; otherwise combine with base_dir
        pcap_path = Path(pcap_file).expanduser()
        if not pcap_path.is_absolute():
            pcap_path = base_dir / pcap_file
        pcap_path = pcap_path.resolve()
    else:
        pcap_path = base_dir / "traffic.pcap"

    if not pcap_path.exists():
        return {
            "error": f"PCAP file not found: {pcap_path}",
            "total_packets": 0,
            "pcap_file": str(pcap_path)
        }

    try:
        packets = run_tshark_command(pcap_path, limit=max_packets)

        if not packets:
            return {
                "error": "No packets found in PCAP file",
                "total_packets": 0,
                "pcap_file": str(pcap_path)
            }

        # Extract protocol distribution
        protocols = {}
        source_ips = {}
        dest_ips = {}
        ports = {}

        for packet in packets:
            layers = packet.get("_source", {}).get("layers", {})

            # Count protocols
            for proto in layers.keys():
                protocols[proto] = protocols.get(proto, 0) + 1

            # Track IPs
            if "ip" in layers:
                src = layers["ip"].get("ip.src", "unknown")
                dst = layers["ip"].get("ip.dst", "unknown")
                source_ips[src] = source_ips.get(src, 0) + 1
                dest_ips[dst] = dest_ips.get(dst, 0) + 1

            # Track ports
            if "tcp" in layers:
                src_port = layers["tcp"].get("tcp.srcport", "unknown")
                dst_port = layers["tcp"].get("tcp.dstport", "unknown")
                ports[src_port] = ports.get(src_port, 0) + 1
                ports[dst_port] = ports.get(dst_port, 0) + 1

            if "udp" in layers:
                src_port = layers["udp"].get("udp.srcport", "unknown")
                dst_port = layers["udp"].get("udp.dstport", "unknown")
                ports[src_port] = ports.get(src_port, 0) + 1
                ports[dst_port] = ports.get(dst_port, 0) + 1

        return {
            "total_packets_analyzed": len(packets),
            "protocol_distribution": protocols,
            "top_source_ips": dict(sorted(source_ips.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_dest_ips": dict(sorted(dest_ips.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_ports": dict(sorted(ports.items(), key=lambda x: x[1], reverse=True)[:10]),
            "pcap_file": str(pcap_path),
        }

    except Exception as e:
        return {"error": str(e), "pcap_file": str(pcap_path)}


@mcp.tool()
def detect_port_scanning(
    pcap_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    threshold: int = 10
) -> Dict:
    """
    Detect potential port scanning activity in PCAP file.

    Args:
        pcap_file: Path to the .pcap file. If not provided, uses traffic.pcap.
        working_dir: Working directory. If not provided, uses current directory.
        threshold: Number of unique ports from same source to consider scanning (default: 10)

    Returns:
        Dictionary with detected port scanning attempts
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if pcap_file:
        # If pcap_file is absolute, use it; otherwise combine with base_dir
        pcap_path = Path(pcap_file).expanduser()
        if not pcap_path.is_absolute():
            pcap_path = base_dir / pcap_file
        pcap_path = pcap_path.resolve()
    else:
        pcap_path = base_dir / "traffic.pcap"

    if not pcap_path.exists():
        return {
            "error": f"PCAP file not found: {pcap_path}",
            "port_scan_detected": False,
            "pcap_file": str(pcap_path)
        }

    try:
        # Get TCP SYN packets (typical port scan signature)
        packets = run_tshark_command(
            pcap_path,
            display_filter="tcp.flags.syn == 1 and tcp.flags.ack == 0",
            limit=5000
        )

        # Track source IP -> destination ports
        scan_attempts = {}

        for packet in packets:
            layers = packet.get("_source", {}).get("layers", {})

            if "ip" in layers and "tcp" in layers:
                src_ip = layers["ip"].get("ip.src", "unknown")
                dst_ip = layers["ip"].get("ip.dst", "unknown")
                dst_port = layers["tcp"].get("tcp.dstport", "unknown")

                key = f"{src_ip}->{dst_ip}"

                if key not in scan_attempts:
                    scan_attempts[key] = {
                        "source_ip": src_ip,
                        "target_ip": dst_ip,
                        "ports": set(),
                        "packet_count": 0
                    }

                scan_attempts[key]["ports"].add(dst_port)
                scan_attempts[key]["packet_count"] += 1

        # Filter for suspicious activity
        suspicious = []
        for key, data in scan_attempts.items():
            if len(data["ports"]) >= threshold:
                suspicious.append({
                    "source_ip": data["source_ip"],
                    "target_ip": data["target_ip"],
                    "unique_ports_scanned": len(data["ports"]),
                    "total_syn_packets": data["packet_count"],
                    "ports_sample": sorted(list(data["ports"]))[:20],
                    "severity": "high" if len(data["ports"]) > 50 else "medium"
                })

        return {
            "port_scan_detected": len(suspicious) > 0,
            "total_suspicious_sources": len(suspicious),
            "suspicious_activity": sorted(suspicious, key=lambda x: x["unique_ports_scanned"], reverse=True),
            "detection_threshold": threshold,
            "pcap_file": str(pcap_path)
        }

    except Exception as e:
        return {"error": str(e), "pcap_file": str(pcap_path)}


@mcp.tool()
def detect_http_anomalies(
    pcap_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict:
    """
    Detect suspicious HTTP traffic patterns (directory enumeration, scanners, etc.).

    Args:
        pcap_file: Path to the .pcap file. If not provided, uses traffic.pcap.
        working_dir: Working directory. If not provided, uses current directory.

    Returns:
        Dictionary with detected HTTP anomalies
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if pcap_file:
        # If pcap_file is absolute, use it; otherwise combine with base_dir
        pcap_path = Path(pcap_file).expanduser()
        if not pcap_path.is_absolute():
            pcap_path = base_dir / pcap_file
        pcap_path = pcap_path.resolve()
    else:
        pcap_path = base_dir / "traffic.pcap"

    if not pcap_path.exists():
        return {
            "error": f"PCAP file not found: {pcap_path}",
            "http_anomalies_detected": False,
            "pcap_file": str(pcap_path)
        }

    try:
        # Get HTTP requests
        packets = run_tshark_command(
            pcap_path,
            display_filter="http.request",
            limit=5000
        )

        # Track HTTP activity per source IP
        http_activity = {}
        suspicious_patterns = []

        scanner_user_agents = [
            "gobuster", "dirbuster", "nikto", "sqlmap", "burp", "zap",
            "nmap", "masscan", "python-requests", "curl", "wget"
        ]

        enumeration_paths = [
            "/.env", "/admin", "/backup", "/.git", "/config", "/db",
            "/.aws", "/api/", "/swagger", "/.well-known"
        ]

        for packet in packets:
            layers = packet.get("_source", {}).get("layers", {})

            if "ip" in layers and "http" in layers:
                src_ip = layers["ip"].get("ip.src", "unknown")
                http = layers["http"]

                user_agent = http.get("http.user_agent", "")
                request_uri = http.get("http.request.uri", "")
                method = http.get("http.request.method", "")
                host = http.get("http.host", "")

                if src_ip not in http_activity:
                    http_activity[src_ip] = {
                        "request_count": 0,
                        "paths": [],
                        "user_agents": set(),
                        "methods": [],
                        "hosts": set()
                    }

                http_activity[src_ip]["request_count"] += 1
                http_activity[src_ip]["paths"].append(request_uri)
                http_activity[src_ip]["user_agents"].add(user_agent)
                http_activity[src_ip]["methods"].append(method)
                http_activity[src_ip]["hosts"].add(host)

                # Check for scanner user agents
                if any(scanner.lower() in user_agent.lower() for scanner in scanner_user_agents):
                    suspicious_patterns.append({
                        "type": "scanner_user_agent",
                        "source_ip": src_ip,
                        "user_agent": user_agent,
                        "path": request_uri,
                        "severity": "high"
                    })

                # Check for enumeration paths
                if any(enum_path in request_uri for enum_path in enumeration_paths):
                    suspicious_patterns.append({
                        "type": "enumeration_path",
                        "source_ip": src_ip,
                        "path": request_uri,
                        "severity": "medium"
                    })

        # Analyze per-IP patterns
        anomalies = []
        for src_ip, activity in http_activity.items():
            # High request volume
            if activity["request_count"] > 50:
                anomalies.append({
                    "type": "high_request_volume",
                    "source_ip": src_ip,
                    "request_count": activity["request_count"],
                    "severity": "medium"
                })

            # Many unique paths (likely enumeration)
            unique_paths = len(set(activity["paths"]))
            if unique_paths > 20:
                anomalies.append({
                    "type": "directory_enumeration",
                    "source_ip": src_ip,
                    "unique_paths": unique_paths,
                    "sample_paths": list(set(activity["paths"]))[:10],
                    "severity": "high"
                })

        return {
            "http_anomalies_detected": len(anomalies) > 0 or len(suspicious_patterns) > 0,
            "total_http_requests": sum(a["request_count"] for a in http_activity.values()),
            "unique_source_ips": len(http_activity),
            "anomalies": anomalies,
            "suspicious_patterns": suspicious_patterns[:20],  # Limit output
            "pcap_file": str(pcap_path)
        }

    except Exception as e:
        return {"error": str(e), "pcap_file": str(pcap_path)}


@mcp.tool()
def detect_data_exfiltration(
    pcap_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    threshold_bytes: int = 1000000
) -> Dict:
    """
    Detect potential data exfiltration (large outbound transfers).

    Args:
        pcap_file: Path to the .pcap file. If not provided, uses traffic.pcap.
        working_dir: Working directory. If not provided, uses current directory.
        threshold_bytes: Minimum bytes to consider suspicious (default: 1MB)

    Returns:
        Dictionary with detected data exfiltration attempts
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if pcap_file:
        # If pcap_file is absolute, use it; otherwise combine with base_dir
        pcap_path = Path(pcap_file).expanduser()
        if not pcap_path.is_absolute():
            pcap_path = base_dir / pcap_file
        pcap_path = pcap_path.resolve()
    else:
        pcap_path = base_dir / "traffic.pcap"

    if not pcap_path.exists():
        return {
            "error": f"PCAP file not found: {pcap_path}",
            "exfiltration_detected": False,
            "pcap_file": str(pcap_path)
        }

    try:
        # Get all TCP packets
        packets = run_tshark_command(pcap_path, display_filter="tcp", limit=10000)

        # Track data transfer per connection
        connections = {}

        for packet in packets:
            layers = packet.get("_source", {}).get("layers", {})

            if "ip" in layers and "tcp" in layers:
                src_ip = layers["ip"].get("ip.src", "unknown")
                dst_ip = layers["ip"].get("ip.dst", "unknown")
                src_port = layers["tcp"].get("tcp.srcport", "unknown")
                dst_port = layers["tcp"].get("tcp.dstport", "unknown")

                # Get packet length
                length = int(layers.get("frame", {}).get("frame.len", 0))

                conn_key = f"{src_ip}:{src_port}->{dst_ip}:{dst_port}"

                if conn_key not in connections:
                    connections[conn_key] = {
                        "source_ip": src_ip,
                        "dest_ip": dst_ip,
                        "source_port": src_port,
                        "dest_port": dst_port,
                        "total_bytes": 0,
                        "packet_count": 0
                    }

                connections[conn_key]["total_bytes"] += length
                connections[conn_key]["packet_count"] += 1

        # Find large transfers
        suspicious = []
        for conn_key, data in connections.items():
            if data["total_bytes"] >= threshold_bytes:
                suspicious.append({
                    "source_ip": data["source_ip"],
                    "dest_ip": data["dest_ip"],
                    "source_port": data["source_port"],
                    "dest_port": data["dest_port"],
                    "total_bytes": data["total_bytes"],
                    "total_mb": round(data["total_bytes"] / 1024 / 1024, 2),
                    "packet_count": data["packet_count"],
                    "severity": "high" if data["total_bytes"] > 10000000 else "medium"
                })

        return {
            "exfiltration_detected": len(suspicious) > 0,
            "suspicious_transfers": sorted(suspicious, key=lambda x: x["total_bytes"], reverse=True),
            "threshold_bytes": threshold_bytes,
            "pcap_file": str(pcap_path)
        }

    except Exception as e:
        return {"error": str(e), "pcap_file": str(pcap_path)}


@mcp.tool()
def get_traffic_timeline(
    pcap_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    interval_seconds: int = 60
) -> Dict:
    """
    Get traffic timeline showing activity over time.

    Args:
        pcap_file: Path to the .pcap file. If not provided, uses traffic.pcap.
        working_dir: Working directory. If not provided, uses current directory.
        interval_seconds: Time interval for grouping packets (default: 60)

    Returns:
        Dictionary with traffic timeline
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if pcap_file:
        # If pcap_file is absolute, use it; otherwise combine with base_dir
        pcap_path = Path(pcap_file).expanduser()
        if not pcap_path.is_absolute():
            pcap_path = base_dir / pcap_file
        pcap_path = pcap_path.resolve()
    else:
        pcap_path = base_dir / "traffic.pcap"

    if not pcap_path.exists():
        return {
            "error": f"PCAP file not found: {pcap_path}",
            "pcap_file": str(pcap_path)
        }

    try:
        packets = run_tshark_command(pcap_path, limit=10000)

        timeline = {}

        for packet in packets:
            layers = packet.get("_source", {}).get("layers", {})
            frame = layers.get("frame", {})

            # Get timestamp
            timestamp_epoch = frame.get("frame.time_epoch", "0")
            timestamp = int(float(timestamp_epoch))

            # Round to interval
            interval_key = (timestamp // interval_seconds) * interval_seconds

            if interval_key not in timeline:
                timeline[interval_key] = {
                    "timestamp": interval_key,
                    "packet_count": 0,
                    "protocols": {}
                }

            timeline[interval_key]["packet_count"] += 1

            # Count protocols
            for proto in layers.keys():
                if proto not in timeline[interval_key]["protocols"]:
                    timeline[interval_key]["protocols"][proto] = 0
                timeline[interval_key]["protocols"][proto] += 1

        # Convert to sorted list
        timeline_list = sorted(timeline.values(), key=lambda x: x["timestamp"])

        return {
            "intervals": timeline_list,
            "interval_seconds": interval_seconds,
            "total_intervals": len(timeline_list),
            "pcap_file": str(pcap_path)
        }

    except Exception as e:
        return {"error": str(e), "pcap_file": str(pcap_path)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
