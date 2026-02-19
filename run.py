#!/usr/bin/env python3
import os
import threading
import sys

def run_bot():
    from bot.main import main
    main()

def run_api():
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("bot.api.webapp_api:app", host="0.0.0.0", port=port)

def run_both():
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    run_bot()

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"
    if mode == "bot":
        run_bot()
    elif mode == "api":
        run_api()
    elif mode == "both":
        run_both()
