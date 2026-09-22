from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from sysmind.tools.contracts import ToolUnavailableError

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


class _CredentialW(ctypes.Structure):
    _fields_ = (
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    )


class WindowsCredentialSecretService:
    """Fixed-namespace current-user Generic Credentials; values never enter SQLite."""

    def __init__(self, namespace: str = "SysMindAI") -> None:
        if os.name != "nt":
            raise ToolUnavailableError("Windows Credential Manager is unavailable.")
        self._namespace = namespace
        self._advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        self._advapi32.CredWriteW.argtypes = (ctypes.POINTER(_CredentialW), wintypes.DWORD)
        self._advapi32.CredWriteW.restype = wintypes.BOOL
        self._advapi32.CredReadW.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CredentialW)),
        )
        self._advapi32.CredReadW.restype = wintypes.BOOL
        self._advapi32.CredDeleteW.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        self._advapi32.CredDeleteW.restype = wintypes.BOOL
        self._advapi32.CredFree.argtypes = (ctypes.c_void_p,)

    def _target(self, key: str) -> str:
        if (
            not key
            or len(key) > 80
            or any(char not in "abcdefghijklmnopqrstuvwxyz._-" for char in key)
        ):
            raise ValueError("Secret reference is invalid.")
        return f"{self._namespace}/{key}"

    def set(self, key: str, value: str) -> None:
        encoded = value.encode("utf-16-le")
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        credential = _CredentialW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = self._target(key)
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "SysMind AI Provider"
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise ToolUnavailableError("Windows could not store the provider credential.")

    def get(self, key: str) -> str | None:
        pointer = ctypes.POINTER(_CredentialW)()
        if not self._advapi32.CredReadW(
            self._target(key), _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)
        ):
            if ctypes.get_last_error() == 1168:
                return None
            raise ToolUnavailableError("Windows could not read the provider credential.")
        try:
            credential = pointer.contents
            data = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return data.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(pointer)

    def delete(self, key: str) -> None:
        if (
            not self._advapi32.CredDeleteW(self._target(key), _CRED_TYPE_GENERIC, 0)
            and ctypes.get_last_error() != 1168
        ):
            raise ToolUnavailableError("Windows could not delete the provider credential.")
