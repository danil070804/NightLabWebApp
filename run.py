#!/usr/bin/env python3
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_api():
    """Запуск API сервера"""
    import uvicorn
    from bot.api.webapp_api import app
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

def run_bot():
    """Запуск Telegram бота"""
    print("🤖 Bot starting...")
    from bot.main import main
    main()

if __name__ == "__main__":
    print("="*50)
    print("🚀 NightLab Bot + WebApp API")
    print("="*50)
    
    # Запускаем API в отдельном потоке
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    
    # Даем API время стартовать
    time.sleep(3)
    
    # Запускаем бота (основной поток)
    run_bot()
