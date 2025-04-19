import os
import json
from typing import Optional
from fastapi import FastAPI
from mcp import ClientSession
from mcp.server import Server
from mcp.client.sse import sse_client
from openai import AsyncOpenAI
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from httpx import HTTPStatusError

load_dotenv()

app = FastAPI()

# Global references
exit_stack = AsyncExitStack()
client_session: Optional[ClientSession] = None
TOOLS = []

openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.on_event("startup")
async def startup_event():
    global client_session, TOOLS
    try:
        client_session = await exit_stack.enter_async_context(sse_client("https://5e1d-2401-4900-1c71-f15d-cf7c-4d3-fecd-e953.ngrok-free.app/sse"))
        await client_session.initialize()
        tool_list = await client_session.list_tools()
        TOOLS.clear()
        TOOLS.extend([
            {"type": "function", "function": tool}
            for tool in tool_list.tools
        ])
        print("✅ Connected to MCP server with tools:", [tool["function"]["name"] for tool in TOOLS])
    except HTTPStatusError as e:
        print(f"❌ Failed to connect to MCP server: HTTP {e.response.status_code} - {e.response.reason_phrase}")
        print(f"Response content: {e.response.text}")
        client_session = None  # Allow app to start without MCP connection
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        client_session = None  # Allow app to start without MCP connection

@app.on_event("shutdown")
async def shutdown_event():
    await exit_stack.aclose()

@app.post("/chat")
async def chat(chat_req: dict):
    try:
        user_msg = chat_req["message"]

        if client_session is None:
            return {"response": "MCP server is not connected. Please try again later."}

        response = await openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": user_msg}],
            tools=TOOLS,
            tool_choice="auto"
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            tool_results = []
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse tool arguments: {str(e)}")
                    continue

                try:
                    result = await client_session.call_tool(fn_name, fn_args)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.content
                    })
                except Exception as e:
                    print(f"❌ Tool call {fn_name} failed: {str(e)}")
                    continue

            followup = await openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": user_msg},
                    msg.model_dump(),
                    *tool_results
                ]
            )
            return {"response": followup.choices[0].message.content}

        return {"response": msg.content}
    except Exception as e:
        print(f"❌ Error in chat endpoint: {str(e)}")
        return {"response": f"An error occurred: {str(e)}"}