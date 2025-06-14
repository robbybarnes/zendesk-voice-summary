#!/bin/bash
# Installation script for voice_summary command line tool

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_SCRIPT="$SCRIPT_DIR/voice_summary"

# Ensure wrapper script exists
if [ ! -f "$WRAPPER_SCRIPT" ]; then
    echo "Error: voice_summary wrapper script not found at $WRAPPER_SCRIPT"
    exit 1
fi

# Create ~/bin directory if it doesn't exist
if [ ! -d "$HOME/bin" ]; then
    echo "Creating ~/bin directory..."
    mkdir -p "$HOME/bin"
fi

# Create symlink
echo "Installing voice_summary to ~/bin..."
rm -f "$HOME/bin/voice_summary" 2>/dev/null
ln -s "$WRAPPER_SCRIPT" "$HOME/bin/voice_summary"

# Check if ~/bin is in PATH
if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo ""
    echo "⚠️  WARNING: ~/bin is not in your PATH"
    echo ""
    echo "To add it to your PATH, add this line to your ~/.zshrc or ~/.bashrc:"
    echo "    export PATH=\"\$HOME/bin:\$PATH\""
    echo ""
    echo "Then reload your shell configuration:"
    echo "    source ~/.zshrc    # For zsh"
    echo "    source ~/.bashrc   # For bash"
    echo ""
    echo "Or for immediate use in this session:"
    echo "    export PATH=\"\$HOME/bin:\$PATH\""
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Usage examples:"
echo "    voice_summary                    # Interactive mode"
echo "    voice_summary 12345              # Process single ticket"
echo "    voice_summary 12345 12346        # Process multiple tickets"
echo "    voice_summary --no-zendesk 12345 # Process without posting to Zendesk"