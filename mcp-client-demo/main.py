import os
import json, logging
from mcp import ClientSession, StdioServerParameters
from typing import Optional
from fastapi import FastAPI
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from httpx import HTTPStatusError

load_dotenv()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_weather",
            "description": "Retrieve current weather information for a specified city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Name of the city to get weather information for."
                    }
                },
                "required": ["city"]
            }
        }
    }
]

# Global references
exit_stack = AsyncExitStack()
client_session: Optional[ClientSession] = None

openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.on_event("startup")
async def startup_event():
    global client_session, TOOLS
    try:
        server_params = StdioServerParameters(
            command="python",
            args=["/home/alphazero/python-apps/server/mcp-server-demo/main.py"],
        )
        reader, writer = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        client_session = await exit_stack.enter_async_context(
            ClientSession(reader, writer)
        )
        await client_session.initialize()
        tool_list = await client_session.list_tools()
        logger.info(f"✅ Connected to MCP server with tools: {tool_list.tools}")
        TOOLS = [
            {"type": "function", "function": tool}
            for tool in tool_list.tools
        ]
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        client_session = None

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
        logger.info(f"✅ Received response: {response}")

        if msg.tool_calls:
            tool_results = []
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Failed to parse tool arguments: {str(e)}")
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
