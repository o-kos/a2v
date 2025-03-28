"""
Converts Amnezia VPN 'vpn://...' key to XRay VLESS url 'vless://...'
configuration file that VLESS client apps can load.

Based on:
https://github.com/amnezia-vpn/amnezia-client/issues/1407

Execute like this in a terminal:

>>> python a2v.py amnezia.key
"""

import argparse
import base64
import configparser
import io
import json
from logging import lastResort
from multiprocessing.managers import rebuild_as_list
from pathlib import Path
import zlib


def from_base64_urlsafe(s: str) -> bytes:
    # Link to StackOverflow answer on how to decode Base64 URL-Safe
    # https://stackoverflow.com/questions/3302946/how-to-decode-base64-url-in-python/9956217#9956217
    return base64.urlsafe_b64decode(s + "=" * (4 - len(s) % 4))


def zlib_decompress_from_qcompress(s: bytes) -> bytes:
    # Link to documentation of qUncompress Qt function
    # https://doc.qt.io/qt-6/qbytearray.html#qUncompress
    # https://doc.qt.io/qtforpython-6/PySide6/QtCore/QtCore_globals.html#PySide6.QtCore.qUncompress
    # Link to an answer that refers to qUncompress function docs and explains
    # that the first 4 bytes need to be skipped if one is uncompressing the data
    # outside of Qt functions
    # https://forum.qt.io/topic/123304/uncompressing-data-python-which-is-compressed-using-qt-quncompress-function/2
    # https://forum.qt.io/post/641554
    s_without_first_four_bytes = s[4:]
    return zlib.decompress(s_without_first_four_bytes)


def extract_data_from_vpn_string(vpn_string: str) -> str:
    # Link to “vpn://...” string decompression code in Amnesia GitHub repository
    # https://github.com/amnezia-vpn/amnezia-client/blob/703b9137e0e903b5b9e8c2de2c123ba98195a859/client/ui/controllers/importController.cpp#L153-L154
    encoded_data = vpn_string.strip("vpn://")
    compressed_data = from_base64_urlsafe(encoded_data)
    decompressed_bytes = zlib_decompress_from_qcompress(compressed_data)
    decompressed_data = decompressed_bytes.decode()
    return decompressed_data


def make_vless_url_from_amnezia_config(client_name, amnezia_config_json: str) -> str:
    amnezia_config = json.loads(amnezia_config_json)
    last_config = amnezia_config["containers"][-1]["xray"]["last_config"]
    last_config = json.loads(last_config)
    outbounds = last_config["outbounds"][0]

    vnext = outbounds["settings"]["vnext"][0]
    address = vnext["address"]
    port = vnext["port"]

    user = vnext["users"][0]
    user_id = user["id"]
    flow = user["flow"]
    encryption = user["encryption"]

    stream_settings = outbounds["streamSettings"]
    security = stream_settings["security"]
    network = stream_settings["network"]

    reality_settings = stream_settings["realitySettings"]
    sni = reality_settings["serverName"]
    fp = reality_settings["fingerprint"]
    pbk = reality_settings["publicKey"]
    sid = reality_settings["shortId"]
    spx = reality_settings["spiderX"] or "/"

    vless_url = (
        f"vless://{user_id}@{address}:{port}"
        f"?security={security}"
        f"&sni={sni}"
        f"&fp={fp}"
        f"&pbk={pbk}"
        f"&sid={sid}"
        f"&spx={spx}"
        f"&type={network}"
        f"&flow={flow}"
        f"&encryption={encryption}"
        f"#{client_name}"
    )

    return vless_url


def run(vpn_file: Path) -> Path:
    vpn_file_content = vpn_file.read_text()

    amnezia_config_json = extract_data_from_vpn_string(vpn_file_content)
    vless_url = make_vless_url_from_amnezia_config(vpn_file.stem, amnezia_config_json)

    vless_url_file = vpn_file.with_suffix(".conf")
    vless_url_file.write_text(vless_url)
    return vless_url_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Converter from Amnezia VPN 'vpn://...' file to "
            "XRay VLESS url '.conf' file"
        ),
        add_help=True,
    )
    parser.add_argument(
        "vpn_file",
        type=Path,
        help="Amnezia VPN key file (usually '.vpn') with 'vpn://...' string",
    )

    args = parser.parse_args()

    resulting_file = run(
        vpn_file=args.vpn_file,
    )
    print(f"Wrote XRay VLESS url config to: {resulting_file}")
