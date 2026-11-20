"""
Minimal Solana helpers using only the standard library:
base58, program-derived addresses (PDA) and JSON-RPC account reads.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import urllib.request

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out


# --- ed25519 curve check (a PDA must NOT be a valid curve point) ---------------
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _on_curve(b: bytes) -> bool:
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P:
        return False
    u = (y * y - 1) % _P
    v = (_D * y * y + 1) % _P
    x = (u * pow(v, 3, _P) * pow(u * pow(v, 7, _P), (_P - 5) // 8, _P)) % _P
    vx2 = (v * x * x) % _P
    if vx2 == u:
        return True
    if vx2 == (-u) % _P:
        return True  # x * sqrt(-1) is the root
    return False


def find_program_address(seeds: list[bytes], program_id: str) -> tuple[str, int]:
    pid = b58decode(program_id)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + pid + b"ProgramDerivedAddress").digest()
        if not _on_curve(h):
            return b58encode(h), bump
    raise ValueError("no PDA found")


# --- RPC ------------------------------------------------------------------------
class SolanaRPC:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get("SOLANA_RPC_URL") or DEFAULT_RPC

    def _call(self, method: str, params: list) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        if "error" in data:
            raise RuntimeError(f"RPC {method}: {data['error']}")
        return data["result"]

    def get_accounts(self, addresses: list[str]) -> list[bytes | None]:
        """Raw account data for up to 100 addresses per call (None if the account does not exist)."""
        out: list[bytes | None] = []
        for i in range(0, len(addresses), 100):
            res = self._call("getMultipleAccounts", [addresses[i:i + 100], {"encoding": "base64"}])
            for acc in res["value"]:
                out.append(base64.b64decode(acc["data"][0]) if acc else None)
        return out


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]
