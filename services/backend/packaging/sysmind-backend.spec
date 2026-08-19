from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


backend_root = Path(SPEC).resolve().parent.parent
source_root = backend_root / "src"

analysis = Analysis(
    [str(source_root / "sysmind" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (str(backend_root / "alembic"), "alembic"),
        (str(backend_root / "alembic.ini"), "."),
    ],
    hiddenimports=collect_submodules("uvicorn"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["mypy", "pytest", "ruff"],
    noarchive=False,
    optimize=1,
)

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="sysmind-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="sysmind-backend",
)
