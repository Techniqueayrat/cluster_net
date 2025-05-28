# Запуск проекта

Этот репозиторий содержит набор микросервисов и графический интерфейс для запуска MPI‑экспериментов в среде GNS3. Для удобства предусмотрен скрипт `run_all.sh`, который запускает все сервисы и GUI.
Должен быть установлен gns3-server.

## Необходимые каталоги и файлы

```
experiment_controller/   – логика управления экспериментом
    main.py
    utils_ssh.py

gns3_manager/             – хранение JSON‑описаний топологий
    main.py
    topologies/
        torus.json        – пример топологии
        torus2.json       – ещё один пример

gns3_vm_manager/         – взаимодействие с GNS3 сервером и управлением ВМ
    main.py

placement_engine/        – вычисление размещения MPI‑процессов
    main.py

metrics_collector/       – сервис измерения времени выполнения
    main.py

gui/                     – Qt‑приложение
    app.py
    controller.py
    widgets.py

requirements.txt          – зависимости Python
run_all.sh                – единый запуск всех сервисов и GUI
```

JSON‑файлы топологий помещаются в папку `gns3_manager/topologies`. В них прописываются пути к QCOW2‑образам для виртуальных машин (пример — `arch3.qcow`).

## Подготовка образа QCOW2

1. Создать минимальную систему (например, на базе Arch Linux).
2. Установить необходимые пакеты:
   ```bash
   pacman -Syu openssh openmpi iproute2 qemu-guest-agent inetutils net-tools tcpdump vim networkmanager
   ```
3. Отключить networkmanager:
   ```bash
   systemctl disable NetworkManager.service
   ```
4. Задаь пароль для пользователя `root` `0000`.
5. Убедиться, что сетевой интерфейс внутри гостя называется `ens3`.

Готовый файл образа (например, `arch3.qcow`) скопировать в каталог `~/GNS3/images/QEMU/`. 

## Запуск

1. Создать .venv среду:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Запустить проект:
   ```bash
   chmod +x run_all.sh
   ./run_all.sh
   ```
   Скрипт поднимет все микросервисы на портах 8000–8004 и откроет GUI.
3. В окне GUI выбрать топологию, тип задачи и стратегию размещения, затем нажать «Запустить эксперимент». Пока обрабатывается только то что стоит по умолчанию.
4. После завершения работы GUI все сервисы будут остановлены автоматически. При перезапуске нужно удалить gns3 проект и проверить не остались ли процессы qemu. Если остались - kill.

