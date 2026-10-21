# -*- mode: python ; coding: utf-8 -*-

app = Analysis(
    ['app.pyw'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(app.pure)
exe = EXE(
    pyz,
    app.scripts,
    [],
    exclude_binaries=True,
    name='DP104_PixelHouse',
    console=False,
    target_arch=None,
)
bundle_files = COLLECT(
    exe,
    app.binaries,
    app.datas,
    strip=False,
    upx=False,
    name='DP104_PixelHouse',
)
app_bundle = BUNDLE(
    bundle_files,
    name='DP104_PixelHouse.app',
    bundle_identifier='com.cxfhackers.dp104pixelhouse',
    info_plist={'NSHighResolutionCapable': True},
)
