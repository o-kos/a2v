"""
Reads an Amnezia VPN backup/config file (Qt settings), extracts each server's
VLESS configuration from the stored XRay config, and writes one importable
'vless://...' URL per output file.

Execute like this in a terminal:

>>> python a2v.py path/to/AmneziaVPN.backup
>>> python a2v.py -o /tmp/out path/to/AmneziaVPN.backup
>>> python a2v.py                       # uses ~/.config/AmneziaVPN.ORG/AmneziaVPN.conf

Based on:
https://github.com/amnezia-vpn/amnezia-client/issues/1407
"""

import argparse
import json
import re
import urllib.parse
from pathlib import Path


DEFAULT_CONF = Path.home() / ".config/AmneziaVPN.ORG/AmneziaVPN.conf"


def qt_unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "0": "\0"}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if nxt == "x" and i + 3 < len(s):
                out.append(chr(int(s[i + 2:i + 4], 16)))
                i += 4
                continue
            if nxt == "u" and i + 5 < len(s):
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_qbytearray_value(text: str, key: str, source: Path) -> str:
    prefix = f'{key}="@ByteArray('
    start = text.find(prefix)
    if start == -1:
        raise SystemExit(f'{key}="@ByteArray(...)" not found in {source}')

    value_start = start + len(prefix)
    terminator = re.search(r'\)"[ \t]*(?:\r?\n|$)', text[value_start:])
    if not terminator:
        raise SystemExit(f'{key}="@ByteArray(...)" is not closed in {source}')
    return text[value_start:value_start + terminator.start()]


def extract_servers_list(conf_path: Path) -> list:
    text = conf_path.read_text(encoding="utf-8")
    payload = extract_qbytearray_value(text, "serversList", conf_path)
    try:
        servers = json.loads(qt_unescape(payload))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"serversList JSON in {conf_path} is invalid: {exc}") from exc
    if not isinstance(servers, list):
        raise SystemExit(f"serversList JSON in {conf_path} is not a list")
    return servers


def find_vless_outbound(server: dict) -> tuple[dict | None, str | None]:
    skip_reason = "no VLESS xray config"
    for c in server.get("containers", []):
        if c.get("container") != "amnezia-xray":
            continue
        cfg_str = c.get("xray", {}).get("last_config")
        if not cfg_str:
            continue
        try:
            cfg = json.loads(cfg_str)
        except json.JSONDecodeError as exc:
            skip_reason = f"invalid xray.last_config JSON: {exc}"
            continue
        for ob in cfg.get("outbounds", []):
            if ob.get("protocol") == "vless":
                return ob, None
    return None, skip_reason


def add_if_present(params: list[tuple[str, str]], key: str, value: object) -> None:
    if value is None or value == "" or value == []:
        return
    if isinstance(value, list):
        params.append((key, ",".join(str(v) for v in value)))
        return
    if isinstance(value, bool):
        params.append((key, str(value).lower()))
        return
    params.append((key, str(value)))


def host_value(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)


def add_security_params(params: list[tuple[str, str]], stream: dict) -> None:
    security = stream.get("security", "none")
    params.append(("security", security))

    if security == "reality":
        rs = stream.get("realitySettings", {})
        params.append(("sni", str(rs.get("serverName", ""))))
        add_if_present(params, "fp", rs.get("fingerprint"))
        add_if_present(params, "pbk", rs.get("publicKey"))
        params.append(("sid", str(rs.get("shortId", ""))))
        params.append(("spx", rs.get("spiderX") or "/"))
        add_if_present(params, "alpn", rs.get("alpn"))
    elif security == "tls":
        ts = stream.get("tlsSettings", {})
        params.append(("sni", str(ts.get("serverName", ""))))
        add_if_present(params, "fp", ts.get("fingerprint"))
        add_if_present(params, "alpn", ts.get("alpn"))
        add_if_present(params, "allowInsecure", ts.get("allowInsecure"))


def add_transport_params(params: list[tuple[str, str]], stream: dict) -> None:
    network = stream.get("network", "tcp")
    params.append(("type", network))

    if network == "tcp":
        settings = stream.get("tcpSettings", {})
        header = settings.get("header", {})
        header_type = header.get("type")
        add_if_present(params, "headerType", header_type)
        request = header.get("request", {})
        headers = request.get("headers", {})
        if "Host" in headers:
            add_if_present(params, "host", host_value(headers["Host"]))
        add_if_present(params, "path", request.get("path"))
    elif network == "ws":
        settings = stream.get("wsSettings", {})
        add_if_present(params, "path", settings.get("path"))
        add_if_present(params, "host", settings.get("headers", {}).get("Host"))
    elif network == "grpc":
        settings = stream.get("grpcSettings", {})
        add_if_present(params, "serviceName", settings.get("serviceName"))
        add_if_present(params, "authority", settings.get("authority"))
        if settings.get("multiMode"):
            params.append(("mode", "multi"))
    elif network in {"http", "h2"}:
        settings = stream.get("httpSettings", {})
        add_if_present(params, "path", settings.get("path"))
        add_if_present(
            params,
            "host",
            host_value(settings["host"]) if "host" in settings else None,
        )
    elif network == "httpupgrade":
        settings = stream.get("httpupgradeSettings", {})
        add_if_present(params, "path", settings.get("path"))
        add_if_present(params, "host", settings.get("host"))
    elif network in {"xhttp", "splithttp"}:
        settings = stream.get("xhttpSettings") or stream.get("splithttpSettings", {})
        add_if_present(params, "path", settings.get("path"))
        add_if_present(params, "host", settings.get("host"))
        add_if_present(params, "mode", settings.get("mode"))
    elif network == "kcp":
        settings = stream.get("kcpSettings", {})
        add_if_present(params, "seed", settings.get("seed"))
        add_if_present(params, "headerType", settings.get("header", {}).get("type"))
    elif network == "quic":
        settings = stream.get("quicSettings", {})
        add_if_present(params, "quicSecurity", settings.get("security"))
        add_if_present(params, "key", settings.get("key"))
        add_if_present(params, "headerType", settings.get("header", {}).get("type"))


def make_vless_url(outbound: dict, name: str) -> str:
    vnext = outbound["settings"]["vnext"][0]
    address = vnext["address"]
    port = vnext["port"]

    user = vnext["users"][0]
    user_id = user["id"]
    flow = user.get("flow", "")
    encryption = user.get("encryption", "none")

    stream = outbound["streamSettings"]

    params: list[tuple[str, str]] = []
    add_security_params(params, stream)
    add_transport_params(params, stream)
    if flow:
        params.append(("flow", flow))
    params.append(("encryption", encryption))

    qs = urllib.parse.urlencode(params)
    fragment = urllib.parse.quote(name, safe="")
    return f"vless://{user_id}@{address}:{port}?{qs}#{fragment}"


def country_code_for(server: dict) -> str:
    api = server.get("api_config", {})
    cc = api.get("server_country_code") or api.get("user_country_code")
    if cc:
        return cc.lower()
    host = (server.get("name") or server.get("description") or "server").lower()
    return re.sub(r"[^a-z0-9]+", "-", host).strip("-") or "xx"


def output_path_for(output_dir: Path, stem: str, used_counts: dict[str, int]) -> Path:
    count = used_counts.get(stem, 0) + 1
    while True:
        suffix = "" if count == 1 else f"-{count}"
        path = output_dir / f"{stem}{suffix}.cfg"
        if not path.exists():
            used_counts[stem] = count
            return path
        count += 1


def run(conf_file: Path, output_dir: Path) -> list[Path]:
    servers = extract_servers_list(conf_file)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    cc_counts: dict[str, int] = {}

    for srv in servers:
        outbound, skip_reason = find_vless_outbound(srv)
        if outbound is None:
            print(f"skip {srv.get('name') or srv.get('description', '?')!r}: {skip_reason}")
            continue

        cc = country_code_for(srv)
        path = output_path_for(output_dir, cc, cc_counts)

        name = srv.get("name") or srv.get("description") or cc
        path.write_text(make_vless_url(outbound, name) + "\n", encoding="utf-8")
        written.append(path)
        print(f"wrote {path}  ({name})")

    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Extract per-server VLESS URLs from an Amnezia VPN backup/config "
            "file and write one .cfg file per server."
        ),
        add_help=True,
    )
    parser.add_argument(
        "conf_file",
        type=Path,
        nargs="?",
        default=DEFAULT_CONF,
        help=f"Path to Amnezia backup/config file (default: {DEFAULT_CONF})",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to write .cfg files (default: current directory)",
    )

    args = parser.parse_args()
    files = run(conf_file=args.conf_file, output_dir=args.output_dir)
    print(f"done: {len(files)} file(s) in {args.output_dir}")
