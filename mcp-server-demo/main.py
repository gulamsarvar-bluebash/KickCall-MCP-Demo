import os
import logging
import asyncio

from mcp.server.fastmcp import Context, FastMCP
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server using STDIO
mcp = FastMCP("Weather App")

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

@mcp.tool()
async def get_weather(city: str) -> dict:
    logger.info(f"[TOOL] Fetching weather for city: {city}")
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OpenWeatherMap API key")

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": api_key, "units": "metric"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    return {
        "city": data["name"],
        "temperature": data["main"]["temp"],
        "description": data["weather"][0]["description"]
    }


if __name__ == "__main__":
    logger.info("Starting STDIO MCP server...")
    try:
        mcp.run(transport='stdio')
        logger.info("STDIO MCP server stopped")
    except Exception as e:
        logger.error(f"STDIO MCP server crashed: {e}", exc_info=True)
