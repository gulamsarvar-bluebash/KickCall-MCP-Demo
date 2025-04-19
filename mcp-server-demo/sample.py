import os
import logging
from mcp.server.fastmcp import Context, FastMCP
import httpx
from urllib.parse import parse_qs
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.responses import Response


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Weather App")
original_sse_app = mcp.sse_app()

# ASGI wrapper
async def debug_sse_app(scope, receive, send):
    print("hello")
    if scope["type"] == "http" and scope["path"] == "/sse":
        qs = scope.get("query_string", b"").decode()
        params = parse_qs(qs)
        logger.info(f"[Debug SSE] params: {params}")
    # Delegate to the real SSE app
    await original_sse_app(scope, receive, send)

# Mount as a sub‑application
app = Starlette(
    routes=[ Mount('/sse', app=mcp.sse_app()) ],
    debug=True,
)


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

@mcp.tool()
async def query_weather(ctx: Context) -> dict:
    city = ctx.params.get("city")
    if not city:
        return {"error": "City parameter is required."}

    weather_data = await get_weather(city)
    return weather_data

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting MCP server on http://0.0.0.0:6277...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=6277)
        logger.info("Server started successfully")
    except Exception as e:
        logger.error(f"Server stopped unexpectedly: {e}", exc_info=True)

# curl -i http://localhost:6277/sse?transportType=sse
