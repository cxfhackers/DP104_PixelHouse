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
    name='DP104-Studio',
    console=False,
    target_arch=None,
)
bundle_files = COLLECT(
    exe,
    app.binaries,
    app.datas,
    strip=False,
    upx=False,
    name='DP104-Studio',
)
app_bundle = BUNDLE(
    bundle_files,
    name='DP104-Studio.app',
    bundle_identifier='com.cxfhackers.dp104studio',
    info_plist={'NSHighResolutionCapable': True},
)
