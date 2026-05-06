# Amnezia Backup to VLESS Converter

[Русская версия](README.ru.md)

`a2v.py` extracts XRay/VLESS server profiles from an Amnezia VPN backup or
configuration file and writes importable `vless://...` URLs.

The script is intended for Amnezia self-hosted XRay profiles stored in the
Amnezia settings backup format. It reads the `serversList="@ByteArray(...)"`
entry, finds VLESS outbounds inside `amnezia-xray` containers, and creates one
`.cfg` file per server.

Based on:
https://github.com/amnezia-vpn/amnezia-client/issues/1407

## Features

- Reads Amnezia VPN backup/config files that contain `serversList`.
- Extracts VLESS outbounds from embedded XRay `last_config` JSON.
- Supports Reality, basic TLS, and common transport-specific parameters.
- Writes one VLESS URL per output file.
- Avoids overwriting existing `.cfg` files by choosing the next free suffix.
- Uses only the Python standard library.

## Requirements

- Python 3.10 or newer.
- No third-party Python packages are required.

## Usage

Run the converter with the path to an Amnezia backup file:

```bash
python3 a2v.py path/to/AmneziaVPN.backup
```

By default, output files are written to the current directory:

```text
de.cfg
nl.cfg
nl-2.cfg
```

To choose an output directory:

```bash
python3 a2v.py -o out path/to/AmneziaVPN.backup
```

If no input file is provided, the script tries to read the local Linux Amnezia
configuration file:

```bash
python3 a2v.py
```

Default path:

```text
~/.config/AmneziaVPN.ORG/AmneziaVPN.conf
```

## Input Format

The input must be a text file in the Amnezia/Qt settings format and contain a
line like:

```text
serversList="@ByteArray(...)"
```

The `serversList` value contains escaped JSON. Each server entry may contain an
`amnezia-xray` container whose `xray.last_config` field is another JSON string
with XRay outbounds.

The script skips servers where it cannot find a VLESS outbound.

## Output Format

Each output `.cfg` file contains a single `vless://...` URL.

File names are based on `api_config.server_country_code` or
`api_config.user_country_code`. If several servers have the same country code,
or if a matching output file already exists, the script appends a numeric
suffix:

```text
de.cfg
de-2.cfg
de-3.cfg
```

If no country code is present, the script derives a file-safe name from the
server name or description.

The URL query string includes security fields such as Reality/TLS settings and
transport fields for common XRay networks such as TCP, WebSocket, gRPC, HTTP,
HTTPUpgrade, XHTTP/SplitHTTP, KCP, and QUIC when those fields are present in the
stored XRay config.

## Security Notes

Treat both input backup files and generated `.cfg` files as sensitive.

Amnezia backups and VLESS URLs can grant access to your VPN server. Do not
publish them, commit them to Git, paste them into issue trackers, or share them
in logs.

If a backup or generated VLESS URL was committed or shared by mistake, remove it
from repository history if needed and rotate the VPN credentials on the server
side.

## Troubleshooting

If the script exits with:

```text
serversList="@ByteArray(...)" not found
```

check that the file is an Amnezia settings backup/config file, not a raw
`vpn://...` key.

If a server is skipped with `no VLESS xray config`, that server either does not
use the `amnezia-xray` container or does not contain a VLESS outbound in its
stored XRay configuration.

If a generated URL does not work in your client, verify that the target client
supports VLESS with the selected security and transport parameters, especially
Reality.
