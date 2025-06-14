# How I Built a Voice Transcription Tool for Zendesk (and Made It a CLI)

At work we've used Zendesk for several years for our ticketing.  In the last few years we've also used the Zendesk Talk voice for the phone (and SMS) as well.  It's not perfect, but it helps keep information about tickets that are phone calls in the same system as everything else.  It records each call, and makes it available via API as well.  This was a great use case for AI, both in helping me build this tool, and using AI endpoints for transcription and summarization. 

Listening to each call and trying to summarize what the issue was and what was done to resolve the issue is tedious.  If the person who received the call can immediately summarize it right after the call that can work, but it's easy to forget something, and if we are busy, it's hard to make the time for it.  Knowing what the issue was and what was done to resolve it is valuable information though, and helps us remain proactive in support instead of always reactive.

So I built a tool to automate the whole process. It downloads voice recordings from Zendesk tickets, transcribes them with OpenAI's Whisper, generates summaries with GPT-4o, and posts everything back to the ticket.

Here's how it works and how I packaged it up as a command-line tool.

## The Basic Architecture

The tool works in three phases:

1. **Download and Transcribe** - Grabs all voice recordings from a ticket and runs them through Whisper
2. **Summarize** - Takes all the transcripts and creates a structured summary with GPT-4o-mini
3. **Post Back** - Adds the summary as a private comment on the ticket.

## File Management

One thing I learned early on - you need a consistent naming scheme or you'll lose track of files fast:

```python
file_basename = f"ticket{ticket_id}_call{call_id}"
audio_file = file_basename + ".mp3"
transcript_file = file_basename + ".txt"
```

This naming convention means I can easily find all files for a ticket, and more importantly, the tool can check if it's already processed something:

```python
if not os.path.exists(transcript_file):
    print("   Transcribing audio with Whisper...")
    transcript = transcribe_audio(audio_file)
    with open(transcript_file, "w", encoding="utf-8") as tf:
        tf.write(transcript)
else:
    if skip_existing:
        print("   Skipping - transcript already exists")
```

This saves a ton of time (and API costs) when reprocessing tickets.

## Handling API Failures

In order to handle potential failures, I built in a simple retry decorator that handles transient failures:

```python
def retry_on_failure(func):
    """Decorator to retry a function on failure."""
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"  Warning: Attempt {attempt + 1} failed: {str(e)}")
                    print(f"  Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"  Error: All {MAX_RETRIES} attempts failed.")
                    raise
        return None
    return wrapper
```

You can add `@retry_on_failure` on any function that makes API calls and you're good to go.

## The Multi-Call Problem

Tickets often have multiple voice recordings - maybe the customer called back, or there were multiple conversations. I needed to handle this scenario, ideally without creating a bunch of individual private comments, making it hard to digest and adding a lot of noise.

For single calls, it's simple - just add a timestamp header:

```python
def summarize_multiple_transcripts(transcripts_data: List[Dict], context: Dict) -> str:
    """Summarize multiple call transcripts into a single comprehensive summary."""
    if len(transcripts_data) == 1:
        # Single call - just add timestamp header
        data = transcripts_data[0]
        timestamp = format_timestamp(data['started_at'])
        summary = summarize_transcript(data['transcript'], context)
        return f"**Call on {timestamp}**\n\n{summary}"

    # Multiple calls - create sections for each
    # ... (builds detailed prompt for GPT-4)
```

The output looks like this:

```markdown
## Call 1 - March 15, 2024 at 10:30 AM MDT
*Duration: 15m 23s | From: +1-555-0123 -> To: +1-555-0456*

### Description of the Call
Customer called about internet connectivity issues...

### Troubleshooting
- Verified modem lights status
- Performed speed test (5 Mbps down, 1 Mbps up)
- Reset modem and router

### Next Steps
- Schedule technician visit for tomorrow
- Follow up email with ticket number

---

## Call 2 - March 15, 2024 at 2:45 PM MDT
*Duration: 8m 12s | From: +1-555-0123 -> To: +1-555-0456*

### Description of the Call
Customer called back to confirm technician appointment...
```

## Making It User-Friendly

I wanted this tool to work both interactively and from the command line. So when you run it without arguments, you get a nice interactive mode:

```bash
$ python voice_summary.py

Zendesk Voice Recording Processor - Interactive Mode
============================================================

Enter ticket numbers or URLs (comma-separated or one per line)
Press Enter twice when done:
12345
12346
https://company.zendesk.com/agent/tickets/12347

Found 3 valid ticket(s): 12345, 12346, 12347

Post summaries to Zendesk? (y/n) [default: y]: y
Skip recordings with existing transcripts? (y/n) [default: n]: y

Processing 3 ticket(s)
   Post to Zendesk: Yes
   Skip existing: Yes

Press Enter to continue or Ctrl+C to cancel...
```

But it also works great for automation:

```python
parser = argparse.ArgumentParser(
    description='Process voice recordings from Zendesk tickets',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog='''
Examples:
  %(prog)s 12345                    # Process single ticket
  %(prog)s 12345 12346 12347        # Process multiple tickets
  %(prog)s --no-zendesk 12345       # Process without posting to Zendesk
  %(prog)s --skip-existing 12345    # Skip tickets with existing transcripts
  %(prog)s https://company.zendesk.com/agent/tickets/12345  # Process from URL
    '''
)
```

## The Progress Display

Here's how it handles progress indicators, which help with longer operations to know that it's still running:

```
Processing Ticket #12345
============================================================
Fetching ticket details...
   Subject: Internet Connection Issues
   Customer: John Smith
   Agent: Support Team
   Status: OPEN

Searching for voice recordings...
   Found 2 voice recording(s)

Phase 1: Downloading and transcribing 2 recording(s)...

Processing recording 1/2 (Call ID: abc123)
   Duration: 15m 23s
   From: +1-555-0123 -> To: +1-555-0456
   Downloading audio...
    Downloaded: ticket12345_callabc123.mp3
   Transcribing audio with Whisper...
   Saved transcript: ticket12345_callabc123.txt

Phase 2: Summarizing 2 transcript(s) with GPT-4o-mini...
   Saved combined summary: ticket12345_combined_summary.txt

Phase 3: Posting combined summary to Zendesk...
   Added private comment to ticket 12345

Ticket #12345 Complete!
   Processed: 2/2 recordings
   Time: 45.2s
```

## Turning It Into a Real Command-Line Tool

Rather than running this directly with python every time, I decided to make it in to a command line tool to make it easier to run from anywhere.

### The Wrapper Script

First, I created a bash wrapper that handles all the environment setup:

```bash
#!/bin/bash
# Wrapper script for voice_summary.py

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
SCRIPT_PATH="$PROJECT_DIR/voice_summary.py"
TRANSCRIPT_DIR="$HOME/zendesk-transcripts"

# Create transcript directory if it doesn't exist
if [ ! -d "$TRANSCRIPT_DIR" ]; then
    echo "Creating transcript directory at $TRANSCRIPT_DIR..."
    mkdir -p "$TRANSCRIPT_DIR"
fi

# Change to transcript directory
cd "$TRANSCRIPT_DIR" || exit 1

# Activate virtual environment if it exists
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
fi

# Execute the Python script with all arguments
python "$SCRIPT_PATH" "$@"
```

This wrapper does a few nice things:
- Creates a dedicated directory for transcripts (`~/zendesk-transcripts`)
- Activates the virtual environment automatically
- Passes all arguments through to the Python script

### Installing It System-Wide

Then I wrote an installation script that sets everything up:

```bash
#!/bin/bash
# Installation script for voice_summary command line tool

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_SCRIPT="$SCRIPT_DIR/voice_summary"

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
    echo "WARNING: ~/bin is not in your PATH"
    echo "To add it, add this line to your ~/.zshrc:"
    echo "    export PATH=\"\$HOME/bin:\$PATH\""
fi
```

After running this, you can use the tool from anywhere:

```bash
$ voice_summary 12345
$ voice_summary  # Interactive mode
```

### Building a Standalone Executable

For distribution, I also created a PyInstaller build script:

```python
# PyInstaller spec file configuration
a = Analysis(
    ['voice_summary.py'],
    hiddenimports=['openai', 'requests'],
    # ... other configuration
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='voice_summary',
    console=True,
    # ... other configuration
)
```

The build script handles everything:

```bash
#!/bin/bash
# Build a standalone executable using PyInstaller

# Install dependencies
pip install -q requests openai pyinstaller

# Build the executable
pyinstaller voice_summary.spec

if [ -f "dist/voice_summary" ]; then
    echo "Build successful!"
    echo "To install system-wide:"
    echo "    sudo cp dist/voice_summary /usr/local/bin/"
fi
```

## Configuration

Instead of hardcoding credentials, the tool uses environment variables:

```python
# Configuration from environment
ZENDESK_DOMAIN = os.getenv('ZENDESK_DOMAIN', 'yourcompany.zendesk.com')
ZENDESK_EMAIL = os.getenv('ZENDESK_EMAIL', '')
ZENDESK_PASSWORD = os.getenv('ZENDESK_PASSWORD', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Validate configuration
if not all([ZENDESK_EMAIL, ZENDESK_PASSWORD, OPENAI_API_KEY]):
    print("Error: Missing required configuration")
    print("Please set the following environment variables:")
    print("  - ZENDESK_EMAIL: Your Zendesk email")
    print("  - ZENDESK_PASSWORD: Your Zendesk password")
    print("  - OPENAI_API_KEY: Your OpenAI API key")
    sys.exit(1)
```

This makes it easy to use across different environments without touching the code.

## Edge Cases I try to Handle

### Closed Tickets

You can't update closed tickets in Zendesk. Instead of just failing, the tool asks what you want to do:

```python
def confirm_closed_ticket_processing() -> bool:
    """Ask user if they want to proceed with processing a closed ticket."""
    print("\nWARNING: This ticket is CLOSED.")
    print("   Closed tickets cannot be updated in Zendesk.")
    while True:
        response = input("\n   Do you still want to process? (y/n): ")
        if response.lower() in ['y', 'yes']:
            return True
        elif response.lower() in ['n', 'no']:
            return False
```

If they proceed, it shows the summary in the console instead of trying to post it.

### Timezone Conversion

The API defaults to using UTC, so I convert everything to Mountain Time:

```python
def format_timestamp(timestamp_str: str) -> str:
    """Convert ISO timestamp to human-readable format in Mountain Time."""
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
    except ImportError:
        from pytz import timezone as ZoneInfo  # Fallback

    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    mountain_tz = ZoneInfo('America/Denver')
    dt_mountain = dt.astimezone(mountain_tz)
    return dt_mountain.strftime("%B %d, %Y at %I:%M %p %Z")
```

### Batch Processing Stats

When processing multiple tickets, you want to know what happened:

```
============================================================
FINAL SUMMARY
============================================================
Tickets processed: 45/50
Recordings processed: 127
Total errors: 5
Total time: 425.3s

Failed tickets:
   - Ticket #12399: 403 Forbidden
   - Ticket #12412: No recordings found
```

## What I Learned

Building this tool taught me a few things:

1. **Phase your processing** - Breaking it into download, transcribe, summarize, and post phases made debugging way easier
2. **Cache aggressively** - Saving transcripts locally saves API calls, and makes it easier to process in general
3. **Make it interactive AND scriptable** - Different use cases need different interfaces
4. **Handle failures gracefully** - APIs will fail, tickets will be closed, permissions will be wrong
5. **Clear progress indicators matter** - Make it easier to know it's still running on longer operations.

## The Results

This tool has been extremely helpful in automating summaries of tickets that were phone calls, making it much easier to determine what was talked about and what resolution was reached, helping us determine where to spend time proactively solving problems, and informing our customers the types of items we have been working on with their employees.