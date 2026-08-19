# Third-party software and licenses

SysMind AI distributes open-source runtime components. Release owners must review the complete locked
dependency graph and preserve all notices required by the corresponding packages. The primary direct
dependencies use the following licenses; the lockfiles are the authoritative version inventory.

| Component family | Purpose | License |
|---|---|---|
| Tauri and official Tauri plugins | Desktop shell, updater, process and single-instance lifecycle | Apache-2.0 OR MIT |
| React | Desktop user interface | MIT |
| FastAPI, Pydantic, pydantic-settings, Uvicorn | Local API and validation | MIT / BSD-3-Clause |
| SQLAlchemy and Alembic | Local persistence and migrations | MIT |
| HTTPX | Provider HTTP client | BSD-3-Clause |
| psutil | Read-only process and system inspection | BSD-3-Clause |
| PyInstaller bootloader | Frozen Python runtime packaging | GPL-2.0-or-later with Bootloader Exception |
| NSIS | Windows installer generation | zlib/libpng |

PyInstaller is a build dependency; its bootloader exception permits distribution of the generated
application subject to the packaged application's own licenses. Microsoft WebView2 is obtained and
licensed under Microsoft's terms; it is not re-licensed by this document.

Before publishing a release:

1. Review `pnpm-lock.yaml`, `apps/desktop/src-tauri/Cargo.lock`, and the resolved Python environment for
   new or changed licenses.
2. Verify every dependency license is compatible with the intended product license and distribution
   model.
3. Add verbatim notices or source offers where a dependency requires them.
4. Record the reviewed dependency inventory with the release artifacts.

This file documents third-party terms only. It does not assign a license to the SysMind AI project
itself; that decision must be made by the project owner before public source or binary distribution.
