"""
Reads AmneziaVPN.conf (Qt INI), extracts each server's VLESS+Reality
configuration, and writes one '<country_code>.cfg' file per server in the
output directory.

Execute like this in a terminal:

>>> python a2v.py                       # uses ~/.config/AmneziaVPN.ORG/AmneziaVPN.conf
>>> python a2v.py path/to/AmneziaVPN.conf
>>> python a2v.py -o /tmp/out path/to/AmneziaVPN.conf

Based on:
https://github.com/amnezia-vpn/amnezia-client/issues/1407
"""

import argparse
import base64
import json
import re
import urllib.parse
import zlib
from pathlib import Path


DEFAULT_CONF = Path.home() / ".config/AmneziaVPN.ORG/AmneziaVPN.conf"


def from_base64_urlsafe(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def zlib_decompress_from_qcompress(s: bytes) -> bytes:
    # Qt's qCompress prepends a 4-byte big-endian uncompressed-size header
    # before a normal zlib stream; skip it before feeding to zlib.decompress.
    # https://doc.qt.io/qt-6/qbytearray.html#qUncompress
    return zlib.decompress(s[4:])


def extract_data_from_vpn_string(vpn_string: str) -> str:
    encoded = vpn_string.strip().removeprefix("vpn://")
    return zlib_decompress_from_qcompress(from_base64_urlsafe(encoded)).decode()


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


def extract_servers_list(conf_path: Path) -> list:
    text = conf_path.read_text(encoding="utf-8")
    m = re.search(
        r'^serversList="@ByteArray\((.*)\)"\s*$',
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise SystemExit(f"serversList=@ByteArray(...) not found in {conf_path}")
    return json.loads(qt_unescape(m.group(1)))


def find_vless_outbound(server: dict) -> dict | None:
    for c in server.get("containers", []):
        if c.get("container") != "amnezia-xray":
            continue
        cfg_str = c.get("xray", {}).get("last_config")
        if not cfg_str:
            continue
        try:
            cfg = json.loads(cfg_str)
        except json.JSONDecodeError:
            continue
        for ob in cfg.get("outbounds", []):
            if ob.get("protocol") == "vless":
                return ob
    return None


def make_vless_url(outbound: dict, name: str) -> str:
    vnext = outbound["settings"]["vnext"][0]
    address = vnext["address"]
    port = vnext["port"]

    user = vnext["users"][0]
    user_id = user["id"]
    flow = user.get("flow", "")
    encryption = user.get("encryption", "none")

    stream = outbound["streamSettings"]
    security = stream.get("security", "none")
    network = stream.get("network", "tcp")

    params: list[tuple[str, str]] = [("security", security)]
    if security == "reality":
        rs = stream.get("realitySettings", {})
        params += [
            ("sni", rs.get("serverName", "")),
            ("fp", rs.get("fingerprint", "")),
            ("pbk", rs.get("publicKey", "")),
            ("sid", rs.get("shortId", "")),
            ("spx", rs.get("spiderX") or "/"),
        ]
    elif security == "tls":
        ts = stream.get("tlsSettings", {})
        if ts.get("serverName"):
            params.append(("sni", ts["serverName"]))
        if ts.get("fingerprint"):
            params.append(("fp", ts["fingerprint"]))
    params.append(("type", network))
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


def run(conf_file: Path, output_dir: Path) -> list[Path]:
    servers = extract_servers_list(conf_file)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    cc_counts: dict[str, int] = {}

    for srv in servers:
        outbound = find_vless_outbound(srv)
        if outbound is None:
            print(f"skip {srv.get('name') or srv.get('description', '?')!r}: no VLESS xray config")
            continue

        cc = country_code_for(srv)
        cc_counts[cc] = cc_counts.get(cc, 0) + 1
        suffix = "" if cc_counts[cc] == 1 else f"-{cc_counts[cc]}"
        path = output_dir / f"{cc}{suffix}.cfg"

        name = srv.get("name") or srv.get("description") or cc
        path.write_text(make_vless_url(outbound, name) + "\n", encoding="utf-8")
        written.append(path)
        print(f"wrote {path}  ({name})")

    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Extract per-server VLESS URLs from AmneziaVPN.conf and write "
            "one '<country_code>.cfg' file per server."
        ),
        add_help=True,
    )
    parser.add_argument(
        "conf_file",
        type=Path,
        nargs="?",
        default=DEFAULT_CONF,
        help=f"Path to AmneziaVPN.conf (default: {DEFAULT_CONF})",
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
