"""Blocking RCSP access for REDMI Headphones Neo over authenticated RFCOMM.

All public I/O methods are serialized. Call this API from a worker thread when
using it from a GUI; it is intentionally synchronous and does not manage an
event loop or Bluetooth pairing.
"""

from __future__ import annotations

import secrets
import socket
import subprocess
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


SERVICE_UUID = "0000fd2d-0000-1000-8000-00805f9b34fb"
NEO_IDENTITIES = {(0x2717, 0x50F0), (0x2717, 0x50FB)}
_MAGIC = b"\xfe\xdc\xba"
_MAX_BODY = 4096


class ProtocolError(Exception):
    """Malformed or unexpected RCSP traffic."""


class AuthenticationError(ProtocolError):
    """The RCSP authentication exchange did not complete."""


class DeviceError(ProtocolError):
    """The earbuds returned a nonzero RCSP status."""

    def __init__(self, opcode: int, status: int):
        super().__init__(f"Earbuds rejected opcode 0x{opcode:02x} (status {status})")
        self.opcode = opcode
        self.status = status


@dataclass(frozen=True)
class NeoSettings:
    noise_mode: int
    noise_level: int
    adaptive_anc: bool


# Port of the replay-verified native Xiaomi authentication response in Auth.kt.
_EXP = []
_v = 1
for _ in range(256):
    _EXP.append(_v & 0xFF)
    _v = (_v * 45) % 257
_LOG = [0] * 256
for _i, _n in enumerate(_EXP):
    _LOG[_n] = _i
_LAYERS = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
    (0, 7, 2, 1, 4, 3, 6, 5, 8, 11, 10, 9, 12, 15, 14, 13),
    (10, 13, 0, 3, 6, 1, 14, 9, 4, 7, 8, 5, 2, 15, 12, 11),
    (14, 7, 0, 13, 8, 15, 6, 11, 4, 9, 2, 5, 10, 1, 12, 3),
)
_GATHER = (14, 7, 8, 15, 0, 13, 6, 11, 4, 9, 2, 5, 10, 1, 12, 3)
_SEED = bytes.fromhex("112233332211")


def _auth_response(challenge: bytes) -> bytes:
    if len(challenge) != 16:
        raise AuthenticationError("Authentication factor must be 16 bytes")
    key = list(challenge)
    key[15] ^= 6
    parity = 0
    for byte in key:
        parity ^= byte
    ring = key + [parity]
    schedule = key[:]
    for s in range(1, 17):
        ring = [((n << 3) | (n >> 5)) & 0xFF for n in ring]
        schedule.extend(
            (ring[(s + i) % 17] + _EXP[_EXP[(17 * (s + 1) + i + 1) % 256]]) & 0xFF
            for i in range(16)
        )
    original = list((_SEED * 3)[:16])
    state = original[:]
    for round_no in range(8):
        if round_no == 2:
            state = [
                n ^ original[i] if (0x9999 >> i) & 1 else (n + original[i]) & 0xFF
                for i, n in enumerate(state)
            ]
        for i in range(16):
            xor_position = (0x9999 >> i) & 1
            n = state[i]
            first, second = schedule[32 * round_no + i], schedule[32 * round_no + 16 + i]
            n = n ^ first if xor_position else (n + first) & 0xFF
            n = _EXP[n] if xor_position else _LOG[n]
            state[i] = (n + second) & 0xFF if xor_position else n ^ second
        for layer in _LAYERS:
            for p in range(0, 16, 2):
                i, j = layer[p], layer[p + 1]
                a, b = state[i], state[j]
                state[i], state[j] = (2 * a + b) & 0xFF, (a + b) & 0xFF
        state = [state[i] for i in _GATHER]
    return bytes(
        n ^ schedule[256 + i] if (0x9999 >> i) & 1 else (n + schedule[256 + i]) & 0xFF
        for i, n in enumerate(state)
    )


def _uuid_matches(value: str) -> bool:
    value = value.lower().removeprefix("0x")
    return value in {"fd2d", "0000fd2d", SERVICE_UUID}


def _sdp_channel(address: str, timeout: float) -> int:
    """Resolve only the RFCOMM endpoint belonging to the Neo RCSP SDP record."""
    import shutil
    try:
        return _sdp_channel_native(address)
    except ProtocolError:
        if not shutil.which('sdptool'): raise
    try:
        result = subprocess.run(
            ["sdptool", "browse", "--xml", address],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtocolError(f"Could not query SDP for {SERVICE_UUID}: {exc}") from exc
    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError as exc:
        raise ProtocolError("sdptool returned invalid SDP XML") from exc

    for record in root.iter():
        if record.tag.rsplit("}", 1)[-1].lower() != "record":
            continue
        service = False
        for attr in record:
            if attr.attrib.get("id", "").lower() not in {"0x0001", "0x1"}:
                continue
            service = any(
                node.tag.rsplit("}", 1)[-1].lower() == "uuid"
                and _uuid_matches(node.attrib.get("value", ""))
                for node in attr.iter()
            )
        if not service:
            continue
        for attr in record:
            if attr.attrib.get("id", "").lower() not in {"0x0004", "0x4"}:
                continue
            # RFCOMM is protocol UUID 0x0003 followed by its uint8 channel.
            for seq in attr.iter():
                children = list(seq)
                if not children or children[0].tag.rsplit("}", 1)[-1].lower() != "uuid":
                    continue
                if children[0].attrib.get("value", "").lower().removeprefix("0x") != "0003":
                    continue
                for child in children[1:]:
                    if child.tag.rsplit("}", 1)[-1].lower() in {"uint8", "uint16"}:
                        try:
                            text = child.attrib["value"]
                            try:
                                channel = int(text, 0)
                            except ValueError:
                                channel = int(text, 16)
                        except (KeyError, ValueError):
                            continue
                        if 1 <= channel <= 30:
                            return channel
    raise ProtocolError(f"SDP has no RFCOMM channel for {SERVICE_UUID}")


def _sdp_channel_native(address: str) -> int:
    """Resolve the service with libbluetooth when sdptool is not installed."""
    import ctypes as c
    import ctypes.util
    libname = ctypes.util.find_library('bluetooth')
    if not libname: raise ProtocolError('BlueZ libbluetooth is unavailable')
    lib = c.CDLL(libname, use_errno=True)
    class Bdaddr(c.Structure): _fields_ = [('b', c.c_uint8 * 6)]
    class UuidValue(c.Union): _fields_ = [('short', c.c_uint16), ('long', c.c_uint32), ('full', c.c_uint8 * 16)]
    class Uuid(c.Structure): _fields_ = [('type', c.c_uint8), ('value', UuidValue)]
    class List(c.Structure): pass
    ListPtr = c.POINTER(List)
    List._fields_ = [('next', ListPtr), ('data', c.c_void_p)]
    lib.str2ba.argtypes = [c.c_char_p, c.POINTER(Bdaddr)]
    lib.sdp_connect.argtypes = [c.POINTER(Bdaddr), c.POINTER(Bdaddr), c.c_uint32]; lib.sdp_connect.restype = c.c_void_p
    lib.sdp_uuid16_create.argtypes = [c.POINTER(Uuid), c.c_uint16]
    lib.sdp_list_append.argtypes = [ListPtr, c.c_void_p]; lib.sdp_list_append.restype = ListPtr
    lib.sdp_service_search_attr_req.argtypes = [c.c_void_p, ListPtr, c.c_int, ListPtr, c.POINTER(ListPtr)]
    lib.sdp_get_access_protos.argtypes = [c.c_void_p, c.POINTER(ListPtr)]
    lib.sdp_get_proto_port.argtypes = [ListPtr, c.c_int]
    lib.sdp_list_free.argtypes = [ListPtr, c.c_void_p]
    lib.sdp_record_free.argtypes = [c.c_void_p]
    lib.sdp_close.argtypes = [c.c_void_p]
    src, dst = Bdaddr(), Bdaddr()
    if lib.str2ba(address.encode('ascii'), c.byref(dst)) != 0: raise ProtocolError('Invalid Bluetooth address')
    session = lib.sdp_connect(c.byref(src), c.byref(dst), 1)
    if not session: raise ProtocolError('Could not connect to the headphone SDP service')
    search = attrs = response = ListPtr()
    try:
        uid = Uuid(); lib.sdp_uuid16_create(c.byref(uid), 0xfd2d)
        attr_range = c.c_uint32(0x0000ffff)
        search = lib.sdp_list_append(None, c.cast(c.byref(uid), c.c_void_p))
        attrs = lib.sdp_list_append(None, c.cast(c.byref(attr_range), c.c_void_p))
        if not search or not attrs: raise ProtocolError('Could not allocate SDP query')
        if lib.sdp_service_search_attr_req(session, search, 2, attrs, c.byref(response)) != 0:
            raise ProtocolError('Could not query the headphone SDP service')
        node = response
        while node:
            protocols = ListPtr()
            if lib.sdp_get_access_protos(node.contents.data, c.byref(protocols)) == 0:
                try:
                    channel = lib.sdp_get_proto_port(protocols, 3)
                    if 1 <= channel <= 30: return channel
                finally:
                    lib.sdp_list_free(protocols, None)
            node = node.contents.next
        raise ProtocolError(f'SDP has no RFCOMM channel for {SERVICE_UUID}')
    finally:
        node = response
        while node:
            lib.sdp_record_free(node.contents.data)
            node = node.contents.next
        if response: lib.sdp_list_free(response, None)
        if attrs: lib.sdp_list_free(attrs, None)
        if search: lib.sdp_list_free(search, None)
        lib.sdp_close(session)


class _Decoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, int, int, int, bytes]]:
        self.buffer.extend(chunk)
        packets = []
        while True:
            start = self.buffer.find(_MAGIC)
            if start < 0:
                keep = 2 if self.buffer.endswith(_MAGIC[:2]) else 1 if self.buffer.endswith(_MAGIC[:1]) else 0
                if keep:
                    del self.buffer[:-keep]
                else:
                    self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 7:
                break
            length = int.from_bytes(self.buffer[5:7], "big")
            if length > _MAX_BODY:
                del self.buffer[0]
                continue
            packet_length = length + 8
            if len(self.buffer) < packet_length:
                break
            raw = bytes(self.buffer[:packet_length])
            if raw[-1] != 0xEF:
                del self.buffer[0]
                continue
            flags, opcode = raw[3], raw[4]
            body = raw[7:-1]
            is_request = bool(flags & 0x80)
            minimum = 2 if (not is_request or opcode == 1) else 1
            if len(body) < minimum:
                del self.buffer[0]
                continue
            status = body[0] if not is_request else 0
            seq = body[0] if is_request else body[1]
            payload_start = (2 if opcode == 1 else 1) if is_request else 2
            payload = body[payload_start:]
            packets.append((flags, opcode, seq, status, payload))
            del self.buffer[:packet_length]
        return packets


class NeoProtocol:
    """One authenticated Neo RFCOMM session; use :meth:`connect` to create it."""

    def __init__(self, sock: socket.socket, timeout: float = 8.0):
        self._socket = sock
        self._timeout = timeout
        self._lock = threading.RLock()
        self._decoder = _Decoder()
        self._packets = []
        self._sequence = 0
        self._closed = False
        self._authenticated = False
        self._peer_challenge = False
        self._peer_verified = False
        self.vid: Optional[int] = None
        self.pid: Optional[int] = None
        self.firmware: Optional[str] = None

    @classmethod
    def connect(cls, address: str, *, channel: Optional[int] = None, timeout: float = 8.0) -> "NeoProtocol":
        """Resolve the Neo service by SDP, connect, authenticate, and verify identity."""
        if not isinstance(address, str) or len(address.split(":")) != 6:
            raise ValueError("address must be a Bluetooth MAC address")
        address = address.upper()
        try:
            if any(len(part) != 2 or int(part, 16) > 255 for part in address.split(":")):
                raise ValueError
        except ValueError as exc:
            raise ValueError("address must be a Bluetooth MAC address") from exc
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if channel is None:
            channel = _sdp_channel(address, timeout)
        if not isinstance(channel, int) or not 1 <= channel <= 30:
            raise ValueError("RFCOMM channel must be in 1..30")
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise ProtocolError("This Python/socket build has no Bluetooth RFCOMM support")
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(timeout)
        try:
            sock.connect((address, channel))
            session = cls(sock, timeout)
            session._authenticate_and_identify()
            return session
        except Exception:
            sock.close()
            raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._authenticated = False
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._socket.close()

    def __enter__(self) -> "NeoProtocol":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _send(self, flags: int, opcode: int, body: bytes = b"") -> None:
        if self._closed:
            raise ProtocolError("Session is closed")
        if len(body) > _MAX_BODY:
            raise ProtocolError("RCSP packet is too large")
        self._socket.sendall(_MAGIC + bytes((flags, opcode)) + len(body).to_bytes(2, "big") + body + b"\xef")

    def _next_packet(self) -> tuple[int, int, int, int, bytes]:
        while not self._packets:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise ProtocolError("Earbuds closed the RFCOMM connection")
            self._packets.extend(self._decoder.feed(chunk))
        return self._packets.pop(0)

    def _reply(self, opcode: int, sequence: int, payload: bytes = b"", status: int = 0) -> None:
        self._send(0x04, opcode, bytes((status, sequence)) + payload)

    def _incoming(self, packet: tuple[int, int, int, int, bytes]) -> None:
        flags, opcode, sequence, _status, payload = packet
        if opcode == 0x50:
            if self._authenticated or len(payload) != 17 or payload[0] != 1:
                raise AuthenticationError("Invalid peer authentication challenge")
            self._reply(opcode, sequence, b"\x01" + _auth_response(payload[1:]))
            self._peer_challenge = True
        elif opcode == 0x51:
            self._reply(opcode, sequence, b"\x01")
            if not self._peer_challenge or payload != b"\x01\x00":
                raise AuthenticationError("Earbuds rejected the authentication response")
            self._peer_verified = True
        elif not self._authenticated:
            raise AuthenticationError(f"Unexpected pre-authentication opcode 0x{opcode:02x}")
        elif opcode == 0x0E or flags & 0x40:
            self._reply(opcode, sequence, status=0 if opcode == 0xF4 else 2)

    def _request(self, opcode: int, payload: bytes = b"") -> bytes:
        sequence = self._sequence
        self._sequence = (sequence + 1) & 0xFF
        self._send(0xC4, opcode, bytes((sequence,)) + payload)
        try:
            while True:
                flags, got_opcode, got_sequence, status, data = self._next_packet()
                packet = (flags, got_opcode, got_sequence, status, data)
                if flags & 0x80:
                    self._incoming(packet)
                elif got_opcode == opcode and got_sequence == sequence:
                    if status:
                        raise DeviceError(opcode, status)
                    return data
        except DeviceError:
            raise
        except Exception:
            self.close()
            raise

    def _authenticate_and_identify(self) -> None:
        with self._lock:
            factor = secrets.token_bytes(16)
            try:
                answer = self._request(0x50, b"\x01" + factor)
                if answer != b"\x01" + _auth_response(factor):
                    raise AuthenticationError("Earbud authentication response did not match")
                if self._request(0x51, b"\x01\x00") != b"\x01":
                    raise AuthenticationError("Invalid pairing-result acknowledgment")
                while not self._peer_verified:
                    packet = self._next_packet()
                    if packet[0] & 0x80:
                        self._incoming(packet)
                self._authenticated = True
                info = _target_info(self._request(0x02, b"\xff\xff\xff\xff"))
                vid, pid, firmware = info
                if (vid, pid) not in NEO_IDENTITIES:
                    raise ProtocolError(f"Unsupported device identity {vid:04X}:{pid:04X}; expected REDMI Headphones Neo")
                self.vid, self.pid, self.firmware = vid, pid, firmware
            except Exception:
                self.close()
                raise

    def read_settings(self) -> NeoSettings:
        """Read RCSP configs 0x000B (noise mode/level) and 0x0025 (adaptive ANC)."""
        with self._lock:
            self._ensure_ready()
            values = _config_values(self._request(0xF3, b"\x00\x0b\x00\x25"))
            if 0x000B not in values or 0x0025 not in values:
                raise ProtocolError("Device omitted requested Neo settings")
            noise, adaptive = values[0x000B], values[0x0025]
            if len(noise) != 2 or noise[0] not in (0, 1, 2) or noise[1] > 2:
                raise ProtocolError("Invalid Neo noise config 0x000B")
            if len(adaptive) != 1:
                raise ProtocolError("Invalid Neo adaptive ANC config 0x0025")
            return NeoSettings(noise[0], noise[1], adaptive[0] != 0)

    def set_noise_mode(self, mode: int) -> None:
        """Set Off=0, ANC=1, or Transparency=2 without changing other configs."""
        if mode not in (0, 1, 2):
            raise ValueError("mode must be 0 (Off), 1 (ANC), or 2 (Transparency)")
        with self._lock:
            self._ensure_ready()
            self._request(0x08, bytes((0x02, 0x04, mode)))

    def set_noise_level(self, level: int) -> None:
        """Write config 0x000B as [ANC mode=1, level 0..2], preserving config 0x0025."""
        if level not in (0, 1, 2):
            raise ValueError("level must be 0 (Light), 1 (Medium), or 2 (High)")
        with self._lock:
            self._ensure_ready()
            self._request(0xF2, bytes((4, 0, 11, 1, level)))

    def set_adaptive_anc(self, enabled: bool) -> None:
        """Write config 0x0025 as one byte; other settings are left untouched."""
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be bool")
        with self._lock:
            self._ensure_ready()
            self._request(0xF2, bytes((3, 0, 37, int(enabled))))

    def _ensure_ready(self) -> None:
        if self._closed or not self._authenticated or self.vid != 0x2717 or self.pid not in (0x50F0, 0x50FB):
            raise ProtocolError("Connect and authenticate to a REDMI Headphones Neo first")


def _config_values(data: bytes) -> dict[int, bytes]:
    values = {}
    offset = 0
    while offset < len(data):
        if offset + 3 > len(data):
            raise ProtocolError("Truncated config record")
        length = data[offset]
        if length < 2:
            raise ProtocolError("Invalid config record length")
        end = offset + 1 + length
        if end > len(data):
            raise ProtocolError("Truncated config value")
        config_id = int.from_bytes(data[offset + 1:offset + 3], "big")
        value = data[offset + 3:end]
        if config_id in values and values[config_id] != value:
            raise ProtocolError(f"Conflicting config 0x{config_id:04x}")
        values[config_id] = value
        offset = end
    return values


def _target_info(data: bytes) -> tuple[int, int, str]:
    attrs = {}
    offset = 0
    while offset < len(data):
        length = data[offset]
        end = offset + 1 + length
        if length < 1 or end > len(data):
            raise ProtocolError("Truncated target info")
        attrs[data[offset + 1]] = data[offset + 2:end]
        offset = end
    identity, version = attrs.get(3), attrs.get(1)
    if identity is None or len(identity) != 4 or version is None or len(version) < 2:
        raise ProtocolError("Missing or invalid target identity/version")
    if any((byte >> 4) > 9 or (byte & 0x0F) > 9 for byte in version[:2]):
        raise ProtocolError("Invalid BCD firmware version")
    firmware = ".".join(str(n) for byte in version[:2] for n in (byte >> 4, byte & 0x0F))
    return int.from_bytes(identity[:2], "big"), int.from_bytes(identity[2:], "big"), firmware
