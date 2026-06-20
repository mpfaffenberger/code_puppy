# PyInstaller recipe for the additive, no-Python-toolchain Mist distribution.
from PyInstaller.utils.hooks import collect_all

code_data, code_binaries, code_hidden = collect_all("code_puppy")
mist_data, mist_binaries, mist_hidden = collect_all("mist")

a = Analysis(
    ["mist/__main__.py"],
    pathex=["."],
    binaries=code_binaries + mist_binaries,
    datas=code_data + mist_data + [("mist_logo.png", ".")],
    hiddenimports=code_hidden + mist_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mist",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
