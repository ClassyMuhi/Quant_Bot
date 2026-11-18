"""
Quant_Bot Modern Real-Time Web Station Launcher
Launches high-performance Starlette/Uvicorn dashboard on http://localhost:8000
"""

import sys
import webbrowser
import uvicorn

if __name__ == "__main__":
    url = "http://localhost:8000"
    print("=" * 60)
    print("⚡ Launching Quant_Bot Next-Gen Real-Time Trading Station")
    print(f"🌐 Access Dashboard at: {url}")
    print("=" * 60)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
