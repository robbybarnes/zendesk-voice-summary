#!/bin/bash
# Build a standalone executable using PyInstaller

# Get the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null

# Install dependencies
echo "Installing dependencies..."
pip install -q requests openai pyinstaller

# Create PyInstaller spec file
cat > voice_summary.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['voice_summary.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['openai', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='voice_summary',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
EOF

# Build the executable
echo "Building standalone executable..."
pyinstaller voice_summary.spec

# Check if build was successful
if [ -f "dist/voice_summary" ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "Standalone executable created at: $PROJECT_DIR/dist/voice_summary"
    echo ""
    echo "To install system-wide:"
    echo "    sudo cp dist/voice_summary /usr/local/bin/"
    echo ""
    echo "Or add to your PATH:"
    echo "    export PATH=\"$PROJECT_DIR/dist:\$PATH\""
else
    echo "❌ Build failed!"
    exit 1
fi