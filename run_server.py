import subprocess
import sys
import os
import time
import webbrowser

def run_command(command):
    try:
        subprocess.check_call(command, shell=True)
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("🚀 Initializing Job Bot Server...")
    
    # 1. Install dependencies
    print("📦 Checking dependencies...")
    if not run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]):
        print("❌ Failed to install dependencies. Please check your internet connection.")
        return

    # 2. Install Playwright browsers
    print("🎭 Ensuring Playwright browsers are installed...")
    run_command([sys.executable, "-m", "playwright", "install", "chromium"])

    # 3. Start the server
    print("\n✨ Starting FastAPI Server on http://localhost:5000")
    print("📁 Search Config:", os.path.abspath("search_config.json"))
    print("💡 Press Ctrl+C to stop the server.\n")
    
    # Give it a second to prepare
    time.sleep(1)
    
    # Open the browser automatically
    webbrowser.open("http://localhost:5000")
    
    # Run the app
    try:
        subprocess.run([sys.executable, "app.py"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user.")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")

if __name__ == "__main__":
    main()
