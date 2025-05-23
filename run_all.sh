#!/usr/bin/env bash
# run_all.sh
python -m pip install -r requirements.txt

# Запуск сервисов FastAPI в отдельных терминалах (uvicorn по разным портам)
uvicorn experiment_controller.main:app --port 8000 --reload &
PID_EC=$!
uvicorn gns3_manager.main:app         --port 8001 --reload &
PID_GM=$!
uvicorn gns3_vm_manager.main:app      --port 8002 --reload &
PID_VM=$!
uvicorn placement_engine.main:app     --port 8003 --reload &
PID_PE=$!
uvicorn metrics_collector.main:app    --port 8004 --reload &
PID_MC=$!

# Дать сервисам прогреться секунду
sleep 5

# Запуск GUI (блокирует текущий терминал)
python -m gui.app

# По выходу из GUI — убиваем микросервисы
kill $PID_EC $PID_GM $PID_VM $PID_PE $PID_MC
# Завершаем запущенный gns3server (если остался)
pkill -f gns3server 2>/dev/null || true

