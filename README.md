# a2v
Amnezia VPN application self-hosting VPN (XRay) config converter

a2v is a tool to convert Amnezia VPN application self-hosting VPN (XRay) config (string as `vpn://...`) to VLESS config (string as `vless://...`).

This key string supported in [Nekoray](https://github.com/MatsuriDayo/nekoray) application.

Based on:
https://github.com/amnezia-vpn/amnezia-client/issues/1407

Execute like this in a terminal:

```bash
>>> python a2v.py amnezia.key
```
