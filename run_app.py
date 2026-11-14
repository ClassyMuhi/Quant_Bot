"""
Streamlit Application Launcher for Quant_Bot
"""

import subprocess
import sys

if __name__ == "__main__":
    cmd = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port=8501", "--server.headless=true"]
    print("Launching Quant_Bot Streamlit Application on http://localhost:8501 ...")
    subprocess.run(cmd)

