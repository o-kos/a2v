# Конвертер backup-файла Amnezia в VLESS

[English version](README.md)

`a2v.py` извлекает XRay/VLESS-профили из backup-файла или конфигурационного
файла Amnezia VPN и записывает импортируемые ссылки `vless://...`.

Скрипт рассчитан на self-hosted XRay-профили Amnezia, сохраненные в формате
backup/settings Amnezia. Он читает запись `serversList="@ByteArray(...)"`, ищет
VLESS outbounds внутри контейнеров `amnezia-xray` и создает по одному `.cfg`
файлу на сервер.

Основано на:
https://github.com/amnezia-vpn/amnezia-client/issues/1407

## Возможности

- Читает backup/config файлы Amnezia VPN, содержащие `serversList`.
- Извлекает VLESS outbounds из встроенного JSON `xray.last_config`.
- Поддерживает Reality, базовые TLS-параметры и распространенные параметры
  transport.
- Записывает одну VLESS-ссылку в каждый выходной файл.
- Не перезаписывает существующие `.cfg` файлы, а выбирает следующий свободный
  суффикс.
- Использует только стандартную библиотеку Python.

## Требования

- Python 3.10 или новее.
- Сторонние Python-пакеты не требуются.

## Использование

Запустите скрипт и передайте путь к backup-файлу Amnezia:

```bash
python3 a2v.py path/to/AmneziaVPN.backup
```

По умолчанию выходные файлы записываются в текущую директорию:

```text
de.cfg
nl.cfg
nl-2.cfg
```

Чтобы выбрать директорию для результата:

```bash
python3 a2v.py -o out path/to/AmneziaVPN.backup
```

Если входной файл не указан, скрипт попробует прочитать локальный конфиг
Amnezia на Linux:

```bash
python3 a2v.py
```

Путь по умолчанию:

```text
~/.config/AmneziaVPN.ORG/AmneziaVPN.conf
```

## Формат входных данных

На входе должен быть текстовый файл в формате Amnezia/Qt settings, содержащий
строку вида:

```text
serversList="@ByteArray(...)"
```

Значение `serversList` содержит экранированный JSON. В каждой записи сервера
может быть контейнер `amnezia-xray`, где поле `xray.last_config` содержит еще
одну JSON-строку с XRay outbounds.

Серверы, в которых VLESS outbound не найден, скрипт пропускает.

## Формат результата

Каждый выходной `.cfg` файл содержит одну строку `vless://...`.

Имена файлов берутся из `api_config.server_country_code` или
`api_config.user_country_code`. Если несколько серверов имеют одинаковый код
страны или подходящий выходной файл уже существует, скрипт добавляет числовой
суффикс:

```text
de.cfg
de-2.cfg
de-3.cfg
```

Если кода страны нет, скрипт формирует безопасное имя файла из имени или
описания сервера.

В query string ссылки добавляются security-поля Reality/TLS и transport-поля
для распространенных XRay network: TCP, WebSocket, gRPC, HTTP, HTTPUpgrade,
XHTTP/SplitHTTP, KCP и QUIC, если эти поля есть в сохраненной XRay-конфигурации.

## Безопасность

Считайте входные backup-файлы и созданные `.cfg` файлы чувствительными данными.

Backup-файлы Amnezia и VLESS-ссылки могут давать доступ к вашему VPN-серверу.
Не публикуйте их, не добавляйте в Git, не вставляйте в issue tracker и не
отправляйте в логи.

Если backup или VLESS-ссылка были случайно добавлены в репозиторий или переданы
третьим лицам, при необходимости удалите их из истории репозитория и
перевыпустите VPN-учетные данные на стороне сервера.

## Возможные проблемы

Если скрипт завершается с ошибкой:

```text
serversList="@ByteArray(...)" not found
```

проверьте, что на вход передан backup/config файл Amnezia, а не сырой ключ
`vpn://...`.

Если сервер пропущен с сообщением `no VLESS xray config`, значит этот сервер
либо не использует контейнер `amnezia-xray`, либо в сохраненной XRay-конфигурации
нет VLESS outbound.

Если созданная ссылка не работает в клиенте, убедитесь, что клиент поддерживает
VLESS с выбранными параметрами security/transport, особенно Reality.
