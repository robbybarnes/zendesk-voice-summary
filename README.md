# Zendesk Voice Summary Tool

An automated tool for transcribing and summarizing voice recordings from Zendesk tickets using OpenAI's Whisper and GPT models.

## Features

- Downloads voice recordings from Zendesk tickets
- Transcribes audio using OpenAI Whisper API
- Generates intelligent summaries with GPT-4o-mini
- Posts summaries back to tickets as private comments
- Handles multiple recordings per ticket
- Skip existing transcripts to save time
- Command-line and interactive modes
- Can be packaged as a standalone executable

## Installation

### Prerequisites

- Python 3.7+
- Zendesk account with API access
- OpenAI API key

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/zendesk-voice-summary.git
cd zendesk-voice-summary
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install requests openai
```

4. Set environment variables:
```bash
export ZENDESK_DOMAIN="yourcompany.zendesk.com"
export ZENDESK_EMAIL="your-email@company.com"
export ZENDESK_PASSWORD="your-zendesk-password"
export OPENAI_API_KEY="sk-your-openai-api-key"
```

## Usage

### Interactive Mode

Run without arguments to enter interactive mode:
```bash
python voice_summary.py
```

### Command Line Mode

Process single ticket:
```bash
python voice_summary.py 12345
```

Process multiple tickets:
```bash
python voice_summary.py 12345 12346 12347
```

Process from URL:
```bash
python voice_summary.py https://yourcompany.zendesk.com/agent/tickets/12345
```

### Options

- `--no-zendesk` - Process recordings without posting to Zendesk
- `--skip-existing` - Skip recordings that already have transcripts

### Examples

```bash
# Process without posting to Zendesk
python voice_summary.py --no-zendesk 12345

# Skip existing transcripts
python voice_summary.py --skip-existing 12345 12346
```

## Installation as Command Line Tool

### Option 1: Wrapper Script

Install the wrapper script to use `voice_summary` from anywhere:

```bash
./scripts/install_voice_summary.sh
```

Then use:
```bash
voice_summary 12345
voice_summary  # Interactive mode
```

### Option 2: Standalone Executable

Build a standalone executable with PyInstaller:

```bash
./scripts/build_standalone.sh
```

This creates a self-contained executable in `dist/voice_summary` that can be distributed without Python dependencies.

## How It Works

The tool operates in three phases:

1. **Download & Transcribe**: Downloads MP3 files from Zendesk and transcribes them using Whisper
2. **Summarize**: Creates intelligent summaries with sections for Description, Troubleshooting, and Next Steps
3. **Post to Zendesk**: Adds the summary as a private comment on the ticket

### File Organization

Processed files are saved with this naming convention:
- Audio: `ticket{id}_call{call_id}.mp3`
- Transcripts: `ticket{id}_call{call_id}.txt`
- Combined summaries: `ticket{id}_combined_summary.txt`

When using the wrapper script, files are organized in `~/zendesk-transcripts/`.

## Configuration

Set these environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `ZENDESK_DOMAIN` | Your Zendesk subdomain (e.g., `company.zendesk.com`) | Yes |
| `ZENDESK_EMAIL` | Your Zendesk account email | Yes |
| `ZENDESK_PASSWORD` | Your Zendesk password | Yes |
| `OPENAI_API_KEY` | Your OpenAI API key | Yes |

## Requirements

- Python 3.7+
- `requests` - For Zendesk API calls
- `openai` - For Whisper transcription and GPT summarization

Optional:
- `pytz` - For timezone support (Python < 3.9)
- `pyinstaller` - For building standalone executables

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

Built with:
- [Zendesk API](https://developer.zendesk.com/api-reference)
- [OpenAI Whisper](https://platform.openai.com/docs/guides/speech-to-text)
- [OpenAI GPT](https://platform.openai.com/docs/guides/text-generation)