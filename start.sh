#!/bin/bash
cd ~/RetroHub

echo "1. Освобождаем порты..."
sudo systemctl stop postgresql 2>/dev/null
fuser -k 9099/tcp 2>/dev/null

echo "2. Запускаем микросервисы RetroHub в Docker..."
docker compose up -d

echo "3. Запускаем мост на ноутбуке (host_runner)..."
~/RetroHub/.venv/bin/python ~/RetroHub/host_runner.py &
RUNNER_PID=$!
sleep 2

echo "4. Открываем окно RetroHub Big Picture на ЭЛТ-телевизоре..."
mkdir -p /tmp/retrohub-firefox
firefox --profile /tmp/retrohub-firefox --no-remote --kiosk "http://localhost:8000" &
sleep 3
qdbus org.kde.kglobalaccel /component/kwin invokeShortcut "Window to Previous Screen" 2>/dev/null

echo "====================================================="
echo "RetroHub запущен! Для остановки нажми Ctrl + C"
echo "====================================================="

trap "echo 'Останавливаем систему...'; kill $RUNNER_PID 2>/dev/null; docker compose stop; exit" INT
wait $RUNNER_PID
