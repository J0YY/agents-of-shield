from agents import RunHooks

class ToolLoggingHooks(RunHooks):
    """
    Optional logging hooks so you can see tool calls and results.
    """

    async def on_tool_start(self, context, agent, tool):
        print(
            f"[TOOL START] agent={agent.name}, tool={tool.name}, "
            f"type={tool.__class__.__name__}"
        )

    async def on_tool_end(self, context, agent, tool, result):
        print(
            f"[TOOL END]   agent={agent.name}, tool={tool.name}\n"
            f"  result={result}\n"
            "----------------------------------------"
        )