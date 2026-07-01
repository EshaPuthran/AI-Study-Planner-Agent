import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def _call_mcp_tool_async(tool_name: str, arguments: dict) -> dict:
    """
    Internal asynchronous helper to spawn the MCP Server subprocess via stdio,
    initialize the session, and dispatch the tool execution request.
    Handles decoding of the MCP responses and error parsing.
    """
    # Point to the mcp_server.py script
    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if not result.content:
                if result.isError:
                    return {"status": "error", "message": "Unknown MCP Server error"}
                raise Exception("Empty response from MCP Server")
                
            raw_text = result.content[0].text
            if result.isError:
                return {"status": "error", "message": raw_text}
                
            try:
                return {"status": "success", "data": json.loads(raw_text)}
            except json.JSONDecodeError:
                return {"status": "success", "data": raw_text}

def execute_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Synchronously executes an MCP tool by spawning the FastMCP server,
    calling the tool, and parsing the response.
    Returns: {"status": "success", "data": ...} or {"status": "error", "message": ...}
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop is not None:
            # We are inside an event loop.
            # In Streamlit, this is rare, but if it happens, we must run it differently.
            # Since nest_asyncio is missing, we'll try to execute it as a task.
            raise Exception("Cannot run synchronous MCP client from within a running asyncio loop without nest_asyncio.")
            
        result = asyncio.run(_call_mcp_tool_async(tool_name, arguments))
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}
