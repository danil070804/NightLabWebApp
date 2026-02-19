#!/usr/bin/env python3
"""
Универсальный скрипт запуска NightLab Bot
"""
import sys
import argparse

def run_bot():
    """Запуск Telegram бота"""
    from bot.main import main
    main()

def run_api():
    """Запуск API сервера"""
    import uvicorn
    uvicorn.run("bot.api.webapp_api:app", host="0.0.0.0", port=8000, reload=True)

def run_both():
    """Запуск бота и API одновременно"""
    import asyncio
    import threading
    
    def start_api():
        import uvicorn
        uvicorn.run("bot.api.webapp_api:app", host="0.0.0.0", port=8000)
    
    # Запускаем API в отдельном потоке
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    # Запускаем бота
    from bot.main import main
    main()

def main():
    parser = argparse.ArgumentParser(description="NightLab Bot Launcher")
    parser.add_argument(
        "mode",
        choices=["bot", "api", "both"],
        default="bot",
        nargs="?",
        help="Что запустить: bot (только бот), api (только API), both (оба)"
    )
    
    args = parser.parse_args()
    
    print(f"🚀 Запуск NightLab Bot в режиме: {args.mode}")
    
    if args.mode == "bot":
        run_bot()
    elif args.mode == "api":
        run_api()
    elif args.mode == "both":
        run_both()

if __name__ == "__main__":
    main()
