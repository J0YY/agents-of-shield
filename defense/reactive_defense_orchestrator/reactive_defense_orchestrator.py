# reactive_defense_orchestrator.py
import asyncio
import os
import sys

from agents import Agent, Runner, set_default_openai_api
from agents import set_tracing_disabled

from defense.tarpit_boxes.tpot_agent import TPotAgentContext
from defense.recon_agent_pcap.recon_agent_pcap import ReconAgentPcapContext
from defense.initial_defense_orchestrator.tool_logging_hooks import ToolLoggingHooks


def require_args() -> str:
    """
    CLI arguments for the reactive defense orchestrator:

    - defense_root: a directory under which defense artifacts live (for example,
      T-Pot configuration, logs, or other defense-related state).

    Example:
        python reactive_defense_orchestrator.py ./defense-output
    """
    if len(sys.argv) != 2:
        print(
            "Usage: python reactive_defense_orchestrator.py <defense_root>",
            file=sys.stderr,
        )
        sys.exit(1)

    defense_root = os.path.abspath(sys.argv[1])
    return defense_root


def build_reactive_defense_orchestrator(
    recon_tool,
    honeypot_tool,
) -> Agent:
    """
    Build the 'reactive defense' orchestrator agent.

    This agent is responsible for adjusting existing defenses for a running web
    application by:

      1) Querying a recon agent that summarizes current or recent attack
         activity against the deployment.
      2) Deciding what high-level honeypot strategy should be followed.
      3) Supplying detailed context (including observed target ports) to the
         honeypot agent, which decides concrete honeypots and ports.
    """
    return Agent(
        name="ReactiveDefenseOrchestrator",
        model="gpt-4.1-mini",
        instructions=(
            "You are the Reactive Defense Orchestrator for a running web application.\n\n"
            "Your job is to react to ongoing or recent attacks by deciding a general\n"
            "strategy for honeypot deployment (e.g., scale up, scale down, or maintain\n"
            "coverage) and then delegating the concrete implementation details to a\n"
            "honeypot management agent.\n\n"
            "You do NOT change the application code; you only:\n"
            "- Decide whether to spin up more honeypots, spin some down, or leave the\n"
            "  current deployment unchanged.\n"
            "- Derive and pass detailed context about current attack patterns (including\n"
            "  which ports and protocols are being probed/attacked and how intensely).\n"
            "- Communicate this strategy and context to the honeypot agent, which is\n"
            "  solely responsible for selecting specific honeypot services and port\n"
            "  mappings.\n\n"
            "You have access to two subagent tools:\n\n"
            "1) A recon / monitoring subagent tool:\n"
            "- `check_attack_activity(...)`:\n"
            "  This tool runs a dedicated ReconAgent that inspects telemetry, logs, and\n"
            "  other signals to determine whether the web app is currently under attack\n"
            "  or has seen suspicious activity recently. Treat its output as the source\n"
            "  of truth for at least the following:\n"
            "    * Whether there is an active or recent attack.\n"
            "    * Which protocols or ports are being targeted (for example, TCP/22,\n"
            "      TCP/80, TCP/443, TCP/3389, etc.).\n"
            "    * Any severity, frequency, or confidence indicators it provides.\n"
            "  Pass a single text input that briefly describes the time window and\n"
            "  environment you care about (for example, 'last 5 minutes, production web\n"
            "  app + T-Pot deployment under the given defense_root').\n\n"
            "2) A honeypot orchestration subagent tool:\n"
            "- `run_reactive_honeypots(strategy_text)`:\n"
            "  This tool runs a dedicated TPotAgent that manages T-Pot honeypot services\n"
            "  via docker-compose and related mechanisms.\n\n"
            "  IMPORTANT: You do NOT know which honeypots are available and you MUST\n"
            "  NOT try to specify specific honeypot service names. The honeypot agent is\n"
            "  responsible for listing available honeypots, choosing which particular\n"
            "  ones to run, and deciding which ports they should listen on.\n\n"
            "  You MAY, however, pass concrete information about what ports and\n"
            "  protocols are currently being probed/attacked, and which ports you think\n"
            "  may be probed next, as part of the context the honeypot agent should\n"
            "  consider. The honeypot agent can then decide whether to bind honeypots on\n"
            "  those ports or related ports.\n\n"
            "  You pass a single text argument describing at least:\n"
            "    - A high-level strategy, such as:\n"
            "        * 'scale_up' (spin up more honeypots or broaden coverage),\n"
            "        * 'scale_down' (reduce honeypots to save resources), or\n"
            "        * 'maintain' (keep the current deployment largely unchanged).\n"
            "    - A concise summary of the recon findings:\n"
            "        * Whether attacks are present or not.\n"
            "        * Which protocols/ports/traffic types are most active or risky.\n"
            "        * Any trend or severity information.\n"
            "    - An explicit section listing the ports that are currently being\n"
            "      probed/attacked, and optionally a small set of ports that you believe\n"
            "      may be probed next, for example:\n"
            "          observed_attack_ports: 22, 80, 443\n"
            "          likely_next_ports: 8080, 8443\n"
            "    - Any resource or policy constraints (for example, 'keep total\n"
            "      honeypots <= 3', 'prioritize SSH and HTTP-like traffic', 'avoid\n"
            "      binding directly on production ports if possible', etc.).\n"
            "    - Any preferred focus areas (for example, 'increase coverage for SSH-\n"
            "      and HTTP-like services that mimic a typical Linux web stack').\n\n"
            "  The honeypot agent will then:\n"
            "    - Inspect what honeypot services are available.\n"
            "    - Decide which specific honeypots to start/stop.\n"
            "    - Choose appropriate ports and any docker-compose details, guided by\n"
            "      the ports and strategy you provided.\n\n"
            "Your responsibilities when you are invoked:\n"
            "1) Always begin by calling the recon tool `check_attack_activity` exactly\n"
            "   once. Ask it to analyze attack and probe activity over a short recent\n"
            "   time window (for example, the last 5–10 minutes) for the deployment\n"
            "   associated with the given defense_root.\n"
            "2) Carefully analyze the recon output to determine:\n"
            "   - Whether there is an active or recent attack.\n"
            "   - Which services, protocols, or ports are being targeted.\n"
            "   - Whether the attack intensity is increasing, decreasing, or stable.\n"
            "   - A small set of 'observed_attack_ports' and, when possible, a small set\n"
            "     of 'likely_next_ports' that might be probed soon (for example, common\n"
            "     alternate HTTP/HTTPS ports like 8080 or 8443 if 80/443 are under\n"
            "     active scanning).\n"
            "3) Based on this analysis, choose a high-level honeypot strategy, such as:\n"
            "   - 'scale_up' when there is clear or increasing attack activity and\n"
            "     additional honeypot coverage is warranted.\n"
            "   - 'scale_down' when there is little or no attack activity and resources\n"
            "     could be conserved.\n"
            "   - 'maintain' when the current deployment appears adequate for the\n"
            "     observed level and type of attacks.\n"
            "   You may express more nuanced strategies in natural language (for\n"
            "   example, 'scale up SSH- and HTTP-like coverage slightly, but do not\n"
            "   increase the total honeypots beyond 3').\n"
            "4) Call the `run_reactive_honeypots` tool exactly once with a single text\n"
            "   argument that includes:\n"
            "   - The chosen strategy label (e.g., 'strategy: scale_up').\n"
            "   - A concise but detailed summary of the recon findings.\n"
            "   - An explicit list of observed attack ports and likely next ports, using\n"
            "     clearly labeled lines such as:\n"
            "         observed_attack_ports: 22, 80, 443\n"
            "         likely_next_ports: 8080, 8443\n"
            "   - Any constraints or preferences (for example, limits on the total\n"
            "     number of honeypots or guidance about which traffic types to focus on).\n"
            "   - Explicit instructions that the honeypot agent must decide which\n"
            "     specific honeypots to start/stop and exactly how to bind them to\n"
            "     ports, using the provided port information as guidance rather than\n"
            "     strict requirements.\n"
            "   You must NOT list specific honeypot service names. You also must NOT\n"
            "   require exact port bindings, but you should provide the observed and\n"
            "   likely target ports so the honeypot agent can make informed choices.\n"
            "5) In your final answer, clearly summarize:\n"
            "   - What recon information you observed (including whether an attack is\n"
            "     present and what it targets).\n"
            "   - Which high-level strategy you chose (e.g., scale up / scale down /\n"
            "     maintain) and why.\n"
            "   - The observed attack ports and likely next ports you passed to the\n"
            "     honeypot agent.\n"
            "   - What you instructed the honeypot agent to do in general terms\n"
            "     (for example, 'increase coverage for SSH and HTTP-like services on or\n"
            "     near the observed ports while keeping total honeypots modest').\n\n"
            "Important rules:\n"
            "- Do not attempt to modify application code, application configuration, or\n"
            "  deployment details directly; your only lever is high-level honeypot\n"
            "  strategy and detailed context (including ports) for the honeypot agent.\n"
            "- Always call the recon tool once at the beginning before deciding on a\n"
            "  honeypot strategy.\n"
            "- Always call the honeypot tool exactly once, providing a high-level\n"
            "  strategy and rich context (including observed and likely ports), but\n"
            "  never concrete honeypot service names or mandated port bindings.\n"
            "- Do not ask follow-up questions; assume any paths or context you are given\n"
            "  in the initial task description are correct."
        ),
        tools=[recon_tool, honeypot_tool],
        mcp_servers=[],
    )


async def main() -> None:
    """
    Run the reactive defense orchestrator from the CLI.

    Example:
        python reactive_defense_orchestrator.py ./defense-output
    """
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    defense_root = require_args()

    # The defense_root can be used by the recon and honeypot agents for locating
    # logs, configuration, or other artifacts. The orchestrator itself treats it
    # as contextual information only.
    async with ReconAgentPcapContext() as recon_agent:
        async with TPotAgentContext() as honeypot_agent:
            recon_tool = recon_agent.as_tool(
                tool_name="check_attack_activity",
                tool_description=(
                    "Run the ReconAgent to summarize current or recent attack activity "
                    "against the deployment. The single text input should describe the "
                    "time window and environment of interest (for example, 'last 5 "
                    "minutes, production deployment under defense_root'). The tool "
                    "returns whether there is an attack, which services/ports are "
                    "targeted, trends in activity, and any relevant severity, "
                    "frequency, or confidence information."
                ),
            )

            honeypot_tool = honeypot_agent.as_tool(
                tool_name="run_reactive_honeypots",
                tool_description=(
                    "Run the TPotAgent to adjust honeypot deployment in response to a "
                    "high-level strategy decided by the orchestrator. The single text "
                    "input contains:\n"
                    "  - A strategy label such as 'strategy: scale_up', "
                    "'strategy: scale_down', or 'strategy: maintain'.\n"
                    "  - A concise summary of the recon findings (e.g., which protocols "
                    "    and ports are being targeted, whether attacks are active, and "
                    "    how intense they are).\n"
                    "  - An explicit list (or lists) of ports that are currently being "
                    "    probed/attacked and, optionally, ports that are likely to be "
                    "    probed next, for example:\n"
                    "        observed_attack_ports: 22, 80, 443\n"
                    "        likely_next_ports: 8080, 8443\n"
                    "  - Any constraints or preferences (for example, total honeypot "
                    "    budget, priority protocols, risk tolerance, or guidance about "
                    "    avoiding direct binding to production ports).\n"
                    "  - Explicit guidance that the honeypot agent itself must choose "
                    "    which specific honeypot services to start/stop and which ports "
                    "    to use, using the port lists as input signals rather than strict "
                    "    requirements.\n"
                    "The orchestrator MUST NOT specify concrete honeypot names. It may "
                    "provide concrete ports as observed/likely attack targets, but the "
                    "TPotAgent is responsible for deciding how to map honeypots onto "
                    "those ports or related ports."
                ),
            )

            orchestrator_agent = build_reactive_defense_orchestrator(
                recon_tool=recon_tool,
                honeypot_tool=honeypot_tool,
            )

            task = (
                "Use the recon tool to assess whether the web application deployment "
                "associated with the following defense root is currently under attack, "
                "and if so, how:\n\n"
                f"Defense root (defense_root): {defense_root}\n\n"
                "First, call the `check_attack_activity` tool once, asking it to analyze "
                "attack and probe activity over a short recent time window (for example, "
                "the last 5–10 minutes) for this deployment.\n\n"
                "From the recon output, identify:\n"
                "- Whether there is an active or recent attack.\n"
                "- Which protocols and ports are being targeted (for example, SSH on "
                "  22, HTTP on 80/443, RDP on 3389).\n"
                "- A small set of ports that are currently being probed/attacked "
                "  (observed_attack_ports).\n"
                "- Optionally, a small set of ports that are likely to be probed next "
                "  (likely_next_ports), such as common alternate HTTP/HTTPS ports when "
                "  80/443 are under attack.\n"
                "- Any information about intensity, trends, or severity.\n\n"
                "Then, based on the recon output, decide on a high-level honeypot "
                "strategy, such as scaling up coverage, scaling down to conserve "
                "resources, or maintaining the current deployment.\n\n"
                "After choosing this strategy, call the `run_reactive_honeypots` tool "
                "exactly once with a single text argument that includes:\n"
                "- The chosen strategy label (e.g., 'strategy: scale_up').\n"
                "- A concise summary of the recon findings.\n"
                "- An explicit list of observed_attack_ports and, if applicable, "
                "  likely_next_ports.\n"
                "- Any constraints or preferences about resource usage and focus areas.\n"
                "- Explicit instructions that the honeypot agent must decide which "
                "  specific honeypots to run and how to bind them to ports, using the "
                "  provided port lists as guidance.\n\n"
                "Finally, summarize the recon findings, the strategy you selected, the "
                "ports you passed to the honeypot agent, and the high-level instructions "
                "you sent to the honeypot agent."
            )

            result = await Runner.run(
                orchestrator_agent,
                task,
                hooks=ToolLoggingHooks(),
                max_turns=20,
            )

            print("=== REACTIVE DEFENSE ORCHESTRATOR FINAL OUTPUT ===")
            print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())