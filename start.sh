#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Inplay Screener — скрипт запуска для macOS
# ──────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Проверяем Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установи: brew install python"
    exit 1
fi

PYTHON=$(command -v python3)
echo "🐍 Python: $($PYTHON --version)"

# Создаём venv если нет
if [ ! -d "venv" ]; then
    echo "📦 Создаём виртуальное окружение..."
    $PYTHON -m venv venv
fi

# Активируем venv
source venv/bin/activate

# Устанавливаем зависимости
echo "📦 Устанавливаем зависимости..."
pip install -q -r requirements.txt

# Проверяем .env
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден. Создай его по примеру .env.example"
    exit 1
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "  🚀  Запускаем Inplay Screener..."
echo "  ⏱  Сканирование каждые 60 секунд"
echo "  📲  Алерты → Telegram"
echo "  Ctrl+C для остановки"
echo "══════════════════════════════════════════════════"
echo ""

# Запускаем
python main.py "$@"
