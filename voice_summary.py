#!/usr/bin/env python3
"""
Zendesk Voice Summary Tool
Automatically transcribe and summarize voice recordings from Zendesk tickets
"""

import os
import sys
import time
import requests
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from openai import OpenAI

# --- Configuration ---
# Set these environment variables or modify the defaults below
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
    print("  - ZENDESK_DOMAIN (optional): Your Zendesk domain (default: yourcompany.zendesk.com)")
    sys.exit(1)

AUTH = (ZENDESK_EMAIL, ZENDESK_PASSWORD)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# --- Utility Functions ---
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

def extract_ticket_id(input_str: str) -> Optional[str]:
    """Extract ticket ID from various input formats."""
    # Handle URLs like https://yourcompany.zendesk.com/agent/tickets/29333
    if input_str.startswith('http'):
        ticket_match = re.search(r'/tickets/(\d+)', input_str)
        if ticket_match:
            return ticket_match.group(1)
    else:
        # Handle direct ticket numbers, removing any non-digit characters
        ticket_id = ''.join(filter(str.isdigit, input_str))
        if ticket_id:
            return ticket_id
    return None

def format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def format_timestamp(timestamp_str: str) -> str:
    """Convert ISO timestamp to human-readable format in Mountain Time."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        # Python < 3.9 fallback
        try:
            from pytz import timezone as ZoneInfo
        except ImportError:
            # If no timezone library available, just parse and format in UTC
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return dt.strftime("%B %d, %Y at %I:%M %p UTC")
            except:
                return timestamp_str
    
    try:
        # Parse ISO format timestamp (assuming UTC)
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        
        # Convert to Mountain Time
        mountain_tz = ZoneInfo('America/Denver')  # Handles both MST and MDT
        dt_mountain = dt.astimezone(mountain_tz)
        
        # Format with timezone abbreviation
        return dt_mountain.strftime("%B %d, %Y at %I:%M %p %Z")
    except:
        return timestamp_str

def confirm_closed_ticket_processing() -> bool:
    """Ask user if they want to proceed with processing a closed ticket."""
    print("\nWARNING: This ticket is CLOSED.")
    print("   Closed tickets cannot be updated in Zendesk.")
    while True:
        response = input("\n   Do you still want to process the voice recordings? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("   Please enter 'y' for yes or 'n' for no.")

# --- Zendesk API ---
@retry_on_failure
def get_ticket_details(ticket_id: str) -> Dict:
    """Get overall ticket info (requester, assignee, etc.)"""
    url = f'https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}.json?include=users'
    resp = requests.get(url, auth=AUTH)
    resp.raise_for_status()
    data = resp.json()
    ticket = data['ticket']
    requester_id = ticket.get('requester_id')
    assignee_id = ticket.get('assignee_id')
    users_map = {}
    users = data.get('users', [])
    if not users:
        for uid in (requester_id, assignee_id):
            if uid:
                user_url = f'https://{ZENDESK_DOMAIN}/api/v2/users/{uid}.json'
                uresp = requests.get(user_url, auth=AUTH)
                uresp.raise_for_status()
                udata = uresp.json()
                users.append(udata['user'])
    for user in users:
        users_map[user['id']] = user['name']
    requester = users_map.get(requester_id, 'Customer')
    assignee = users_map.get(assignee_id, 'Agent')
    subject = ticket.get('subject', '')
    description = ticket.get('description', '')
    status = ticket.get('status', '')
    return dict(
        requester=requester,
        assignee=assignee,
        subject=subject,
        description=description,
        status=status
    )

@retry_on_failure
def get_voice_recordings(ticket_id: str) -> List[Dict]:
    """Return all voice recordings (VoiceComment) on the ticket."""
    url = f'https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/comments.json'
    response = requests.get(url, auth=AUTH)
    response.raise_for_status()
    data = response.json()
    voice_recordings = []
    for comment in data.get('comments', []):
        if comment.get('type') == 'VoiceComment':
            voice_data = comment.get('data', {})
            if voice_data.get('recorded') and voice_data.get('recording_url'):
                voice_recordings.append({
                    "call_id": voice_data.get('call_id'),
                    "recording_url": voice_data.get('recording_url'),
                    "from": voice_data.get('from'),
                    "to": voice_data.get('to'),
                    "duration": voice_data.get('call_duration'),
                    "started_at": voice_data.get('started_at'),
                    "comment_id": comment['id'],
                })
    return voice_recordings

@retry_on_failure
def download_recording(recording_url: str, filename: str) -> bool:
    """Download audio file via Zendesk API auth with progress bar."""
    resp = requests.get(recording_url, auth=AUTH, stream=True)
    resp.raise_for_status()
    
    total_size = int(resp.headers.get('content-length', 0))
    downloaded = 0
    
    with open(filename, 'wb') as f:
        for chunk in resp.iter_content(8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    progress = downloaded / total_size * 100
                    print(f"\r    Downloading: {progress:.1f}%", end='', flush=True)
    
    print(f"\r    Downloaded: {filename}")

@retry_on_failure
def add_private_comment(ticket_id: str, comment_body: str, is_closed: bool = False) -> bool:
    """Add a private (non-public) comment with Markdown to the Zendesk ticket."""
    if is_closed:
        print(f"    Warning: Cannot update closed ticket {ticket_id}")
        print("    Summary will be displayed in console instead:")
        print("\n" + "="*50 + " SUMMARY " + "="*50)
        print(comment_body)
        print("="*110 + "\n")
        return True  # Return True since we successfully processed, just didn't post
    
    url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}.json"
    payload = {
        "ticket": {
            "comment": {
                "body": comment_body,
                "public": False
            }
        }
    }
    try:
        resp = requests.put(url, auth=AUTH, json=payload)
        resp.raise_for_status()
        print(f"    Added private comment to ticket {ticket_id}")
        return True
    except Exception as e:
        print(f"    Error adding comment to ticket {ticket_id}: {str(e)}")
        print("    Summary will be displayed in console instead:")
        print("\n" + "="*50 + " SUMMARY " + "="*50)
        print(comment_body)
        print("="*110 + "\n")
        return False

# --- OpenAI APIs ---
@retry_on_failure
def transcribe_audio(file_path: str, model: str = "whisper-1") -> str:
    """Transcribe audio file via OpenAI Whisper."""
    with open(file_path, "rb") as audio_file:
        try:
            response = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format="text"
            )
            return response
        except Exception as e:
            print(f"    Transcription error: {str(e)}")
            raise

@retry_on_failure
def summarize_transcript(transcript: str, context: Dict) -> str:
    """Summarize the call transcript with context via GPT-5."""
    prompt = (
        f"You are a professional support desk call summarizer. "
        f"The customer is '{context['requester']}', and the support agent is '{context['assignee']}'. "
        f"The overall ticket subject is: '{context['subject']}'. "
        f"Write a summary for the following support call transcript. "
        f"Do NOT use any emojis.\n\n"
        f"Create three clear sections, each with a markdown heading: 'Description of the Call', 'Troubleshooting', and 'Next Steps'. "
        f"- Description: Clearly state what specific issue(s) the customer called about\n"
        f"- Troubleshooting: List ALL technical steps discussed or attempted as bullet points\n"
        f"- Next Steps: List ALL follow-up actions or pending items as bullet points\n\n"
        f"Be concise but ensure NO important technical details, troubleshooting steps, or follow-up items are omitted.\n"
        f"--- BEGIN CALL TRANSCRIPT ---\n"
        f"{transcript}\n"
        f"--- END CALL TRANSCRIPT ---"
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You summarize support desk call transcripts for other support agents."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"    Summarization error: {str(e)}")
        raise

@retry_on_failure
def summarize_multiple_transcripts(transcripts_data: List[Dict], context: Dict) -> str:
    """Summarize multiple call transcripts into a single comprehensive summary."""
    if len(transcripts_data) == 1:
        # Single call - just add timestamp header
        data = transcripts_data[0]
        timestamp = format_timestamp(data['started_at']) if data['started_at'] else "Unknown time"
        summary = summarize_transcript(data['transcript'], context)
        return f"**Call on {timestamp}**\n\n{summary}"
    
    # Multiple calls - create sections for each
    prompt_parts = [
        f"You are a professional support desk call summarizer. ",
        f"The customer is '{context['requester']}', and the support agent is '{context['assignee']}'. ",
        f"The overall ticket subject is: '{context['subject']}'. ",
        f"You are summarizing {len(transcripts_data)} separate calls about the same issue. ",
        f"Do NOT use any emojis. Do NOT use ### or any other separators between calls.\n\n",
        f"For EACH call, you MUST capture ALL of the following:\n",
        f"   - The specific issues or problems being addressed in that call\n",
        f"   - All troubleshooting steps discussed or attempted during that call\n",
        f"   - Any follow-up items, next steps, or pending actions from that call\n\n",
        f"Create a summary for EACH call separately, with each call having its own three sections: ",
        f"'Description of the Call', 'Troubleshooting', and 'Next Steps'. ",
        f"- Description: Clearly state what specific issue(s) were discussed in this call\n",
        f"- Troubleshooting: List ALL technical steps discussed or attempted as bullet points\n",
        f"- Next Steps: List ALL follow-up actions or pending items as bullet points\n\n",
        f"Format each call as 'CALL X' where X is the call number.\n",
        f"Be concise but ensure NO important technical details, troubleshooting steps, or follow-up items are omitted from any call.\n\n"
    ]
    
    # Add each transcript with call info
    for i, data in enumerate(transcripts_data, 1):
        timestamp = format_timestamp(data['started_at']) if data['started_at'] else "Unknown time"
        duration = format_duration(data['duration']) if data['duration'] else "Unknown duration"
        
        prompt_parts.extend([
            f"--- CALL {i} of {len(transcripts_data)} ---\n",
            f"Date/Time: {timestamp}\n",
            f"Duration: {duration}\n",
            f"From: {data['from']} -> To: {data['to']}\n",
            f"Call ID: {data['call_id']}\n",
            f"--- BEGIN TRANSCRIPT ---\n",
            f"{data['transcript']}\n",
            f"--- END TRANSCRIPT ---\n\n"
        ])
    
    prompt = ''.join(prompt_parts)
    
    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You summarize support desk call transcripts for other support agents. Format your response clearly with sections for each call."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        # Format the response with clear call headers
        raw_summary = response.choices[0].message.content
        
        # Add call headers to the summary
        formatted_parts = []
        call_summaries = raw_summary.split("CALL")  # Assuming GPT formats with "CALL X" headers
        
        for i, data in enumerate(transcripts_data):
            timestamp = format_timestamp(data['started_at']) if data['started_at'] else "Unknown time"
            duration = format_duration(data['duration']) if data['duration'] else "Unknown duration"
            
            formatted_parts.append(f"## Call {i+1} - {timestamp}")
            formatted_parts.append(f"*Duration: {duration} | From: {data['from']} -> To: {data['to']}*\n")
            
            # Find the corresponding summary section
            if i+1 < len(call_summaries):
                # Extract the summary for this call
                call_summary = call_summaries[i+1].strip()
                # Remove any numbering at the start
                call_summary = re.sub(r'^\d+.*?\n', '', call_summary, count=1)
                # Remove any ### separators
                call_summary = call_summary.replace('###', '').strip()
                formatted_parts.append(call_summary)
                if i < len(transcripts_data) - 1:  # Don't add separator after last call
                    formatted_parts.append("\n---\n")
        
        return '\n'.join(formatted_parts)
        
    except Exception as e:
        print(f"    Summarization error: {str(e)}")
        raise

# --- Processing Functions ---
def process_single_recording(ticket_id: str, rec: Dict, idx: int, total: int, 
                           skip_existing: bool = False) -> Tuple[bool, str, Dict]:
    """Download and transcribe a single voice recording."""
    print(f"\nProcessing recording {idx}/{total} (Call ID: {rec['call_id']})")
    
    if rec['duration']:
        print(f"   Duration: {format_duration(rec['duration'])}")
    if rec['from'] and rec['to']:
        print(f"   From: {rec['from']} -> To: {rec['to']}")
    
    file_basename = f"ticket{ticket_id}_call{rec['call_id']}"
    audio_file = file_basename + ".mp3"
    transcript_file = file_basename + ".txt"
    
    try:
        # Download audio if missing
        if not os.path.exists(audio_file):
            print(f"   Downloading audio...")
            download_recording(rec['recording_url'], audio_file)
        else:
            print(f"   Audio file exists: {audio_file}")
        
        # Transcribe audio
        if not os.path.exists(transcript_file):
            print("   Transcribing audio with Whisper...")
            transcript = transcribe_audio(audio_file)
            with open(transcript_file, "w", encoding="utf-8") as tf:
                tf.write(transcript)
            print(f"   Saved transcript: {transcript_file}")
        else:
            if skip_existing:
                print("   Skipping - transcript already exists")
                # Still load the transcript for summarization
            print("   Loading existing transcript...")
            with open(transcript_file, "r", encoding="utf-8") as tf:
                transcript = tf.read()
        
        # Return transcript and metadata for later summarization
        return True, transcript, {
            'call_id': rec['call_id'],
            'from': rec.get('from', 'Unknown'),
            'to': rec.get('to', 'Unknown'),
            'duration': rec.get('duration', 0),
            'started_at': rec.get('started_at', ''),
            'file_basename': file_basename
        }
        
    except Exception as e:
        print(f"   Error processing recording: {str(e)}")
        return False, "", {}

def process_ticket(ticket_id: str, post_to_zendesk: bool = True, 
                  skip_existing: bool = False) -> Dict:
    """Process all voice recordings for a ticket."""
    start_time = time.time()
    
    print(f"\nProcessing Ticket #{ticket_id}")
    print("=" * 60)
    
    try:
        # Get ticket details
        print("Fetching ticket details...")
        context = get_ticket_details(ticket_id)
        print(f"   Subject: {context['subject']}")
        print(f"   Customer: {context['requester']}")
        print(f"   Agent: {context['assignee']}")
        print(f"   Status: {context['status'].upper()}")
        
        # Check if ticket is closed
        is_closed = context['status'] == 'closed'
        if is_closed:
            if not confirm_closed_ticket_processing():
                print("\n   Info: Skipping closed ticket processing.")
                return {
                    'ticket_id': ticket_id,
                    'status': 'skipped_closed',
                    'recordings_processed': 0,
                    'errors': 0
                }
            # If user confirmed, disable posting to Zendesk
            post_to_zendesk = False
            print("   Info: Processing will continue but summaries will NOT be posted to Zendesk.")
        
        # Get voice recordings
        print("\nSearching for voice recordings...")
        recordings = get_voice_recordings(ticket_id)
        
        if not recordings:
            print("   Info: No voice recordings found for this ticket.")
            return {
                'ticket_id': ticket_id,
                'status': 'no_recordings',
                'recordings_processed': 0,
                'errors': 0
            }
        
        print(f"   Found {len(recordings)} voice recording(s)")
        
        # Phase 1: Download and transcribe all recordings
        print(f"\nPhase 1: Downloading and transcribing {len(recordings)} recording(s)...")
        transcripts_data = []
        successful = 0
        errors = 0
        
        for idx, rec in enumerate(recordings, 1):
            success, transcript, metadata = process_single_recording(
                ticket_id, rec, idx, len(recordings), skip_existing
            )
            
            if success and transcript:
                successful += 1
                transcripts_data.append({
                    'transcript': transcript,
                    **metadata  # Includes call_id, from, to, duration, started_at, file_basename
                })
            else:
                errors += 1
        
        if not transcripts_data:
            print("\nError: No transcripts were successfully processed.")
            return {
                'ticket_id': ticket_id,
                'status': 'failed',
                'error': 'No transcripts processed',
                'recordings_processed': 0,
                'errors': errors
            }
        
        # Phase 2: Summarize all transcripts together
        print(f"\nPhase 2: Summarizing {len(transcripts_data)} transcript(s) with GPT-5...")
        try:
            combined_summary = summarize_multiple_transcripts(transcripts_data, context)
            
            # Save combined summary
            summary_file = f"ticket{ticket_id}_combined_summary.txt"
            with open(summary_file, "w", encoding="utf-8") as sf:
                sf.write(combined_summary)
            print(f"   Saved combined summary: {summary_file}")
            
            # Show preview
            print("\n   Summary Preview:")
            preview_lines = combined_summary.split('\n')[:15]
            for line in preview_lines:
                print(f"      {line}")
            if len(combined_summary.split('\n')) > 15:
                print("      ...")
            
            # Phase 3: Post to Zendesk if enabled
            if post_to_zendesk:
                print("\nPhase 3: Posting combined summary to Zendesk...")
                add_private_comment(ticket_id, combined_summary, is_closed)
            elif is_closed:
                print("\nPhase 3: Cannot post to closed ticket - summary displayed above")
            else:
                print("\nPhase 3: Skipping Zendesk posting as requested")
                
        except Exception as e:
            print(f"\nError: Failed to summarize transcripts: {str(e)}")
            errors += 1
        
        # Summary
        elapsed = time.time() - start_time
        print(f"\nTicket #{ticket_id} Complete!")
        print(f"   Processed: {successful}/{len(recordings)} recordings")
        if errors > 0:
            print(f"   Errors: {errors}")
        print(f"   Time: {elapsed:.1f}s")
        
        return {
            'ticket_id': ticket_id,
            'status': 'completed',
            'recordings_processed': successful,
            'errors': errors,
            'elapsed_time': elapsed
        }
        
    except Exception as e:
        print(f"\nError: Failed to process ticket #{ticket_id}: {str(e)}")
        return {
            'ticket_id': ticket_id,
            'status': 'failed',
            'error': str(e)
        }

# --- Interactive Mode ---
def interactive_mode():
    """Interactive mode for processing tickets when run without arguments."""
    print("\nZendesk Voice Recording Processor - Interactive Mode")
    print("=" * 60)
    
    # Get ticket IDs
    print("\nEnter ticket numbers or URLs (comma-separated or one per line)")
    print("Press Enter twice when done:")
    
    ticket_inputs = []
    while True:
        line = input().strip()
        if not line and ticket_inputs:
            break
        elif line:
            # Handle comma-separated input
            if ',' in line:
                ticket_inputs.extend([t.strip() for t in line.split(',')])
            else:
                ticket_inputs.append(line)
    
    if not ticket_inputs:
        print("Error: No tickets entered. Exiting.")
        return
    
    # Extract ticket IDs
    ticket_ids = []
    for ticket_input in ticket_inputs:
        ticket_id = extract_ticket_id(ticket_input)
        if ticket_id:
            ticket_ids.append(ticket_id)
        else:
            print(f"Warning: Could not extract ticket ID from: {ticket_input}")
    
    if not ticket_ids:
        print("Error: No valid ticket IDs found.")
        return
    
    # Ask about options
    print(f"\nFound {len(ticket_ids)} valid ticket(s): {', '.join(ticket_ids)}")
    
    # Post to Zendesk option
    print("\nPost summaries to Zendesk? (y/n) [default: y]: ", end='')
    post_response = input().strip().lower()
    post_to_zendesk = post_response != 'n'
    
    # Skip existing option
    print("Skip recordings with existing transcripts? (y/n) [default: n]: ", end='')
    skip_response = input().strip().lower()
    skip_existing = skip_response == 'y'
    
    # Confirmation
    print(f"\nProcessing {len(ticket_ids)} ticket(s)")
    print(f"   Post to Zendesk: {'Yes' if post_to_zendesk else 'No'}")
    print(f"   Skip existing: {'Yes' if skip_existing else 'No'}")
    print("\nPress Enter to continue or Ctrl+C to cancel...", end='')
    input()
    
    # Process tickets
    results = []
    total_start = time.time()
    
    for ticket_id in ticket_ids:
        result = process_ticket(
            ticket_id, 
            post_to_zendesk=post_to_zendesk,
            skip_existing=skip_existing
        )
        results.append(result)
    
    # Final summary
    total_elapsed = time.time() - total_start
    successful_tickets = sum(1 for r in results if r.get('status') == 'completed')
    total_recordings = sum(r.get('recordings_processed', 0) for r in results)
    total_errors = sum(r.get('errors', 0) for r in results)
    
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Tickets processed: {successful_tickets}/{len(ticket_ids)}")
    print(f"Recordings processed: {total_recordings}")
    if total_errors > 0:
        print(f"Total errors: {total_errors}")
    print(f"Total time: {total_elapsed:.1f}s")
    
    # List any failed tickets
    failed_tickets = [r for r in results if r.get('status') == 'failed']
    if failed_tickets:
        print("\nFailed tickets:")
        for r in failed_tickets:
            print(f"   - Ticket #{r['ticket_id']}: {r.get('error', 'Unknown error')}")

# --- Main workflow ---
def main():
    # Check if running with command line arguments
    if len(sys.argv) > 1:
        # Command line mode
        parser = argparse.ArgumentParser(
            description='Process voice recordings from Zendesk tickets',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Examples:
  %(prog)s 12345                    # Process single ticket
  %(prog)s 12345 12346 12347        # Process multiple tickets
  %(prog)s --no-zendesk 12345       # Process without posting to Zendesk
  %(prog)s --skip-existing 12345    # Skip tickets with existing transcripts
  %(prog)s https://yourcompany.zendesk.com/agent/tickets/12345  # Process from URL
            '''
        )
        
        parser.add_argument('tickets', nargs='+', 
                           help='Ticket numbers or URLs to process')
        parser.add_argument('--no-zendesk', action='store_true',
                           help='Skip posting summaries to Zendesk')
        parser.add_argument('--skip-existing', action='store_true',
                           help='Skip recordings that already have transcripts')
        
        args = parser.parse_args()
        
        # Extract ticket IDs
        ticket_ids = []
        for ticket_input in args.tickets:
            ticket_id = extract_ticket_id(ticket_input)
            if ticket_id:
                ticket_ids.append(ticket_id)
            else:
                print(f"Warning: Could not extract ticket ID from: {ticket_input}")
        
        if not ticket_ids:
            print("Error: No valid ticket IDs found.")
            sys.exit(1)
        
        # Header
        print("\nZendesk Voice Recording Processor")
        print("=" * 60)
        print(f"Tickets to process: {len(ticket_ids)}")
        print(f"Post to Zendesk: {'Yes' if not args.no_zendesk else 'No'}")
        print(f"Skip existing: {'Yes' if args.skip_existing else 'No'}")
        print("=" * 60)
        
        # Process tickets
        results = []
        total_start = time.time()
        
        for ticket_id in ticket_ids:
            result = process_ticket(
                ticket_id, 
                post_to_zendesk=not args.no_zendesk,
                skip_existing=args.skip_existing
            )
            results.append(result)
        
        # Final summary
        total_elapsed = time.time() - total_start
        successful_tickets = sum(1 for r in results if r.get('status') == 'completed')
        total_recordings = sum(r.get('recordings_processed', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)
        
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)
        print(f"Tickets processed: {successful_tickets}/{len(ticket_ids)}")
        print(f"Recordings processed: {total_recordings}")
        if total_errors > 0:
            print(f"Total errors: {total_errors}")
        print(f"Total time: {total_elapsed:.1f}s")
        
        # List any failed tickets
        failed_tickets = [r for r in results if r.get('status') == 'failed']
        if failed_tickets:
            print("\nFailed tickets:")
            for r in failed_tickets:
                print(f"   - Ticket #{r['ticket_id']}: {r.get('error', 'Unknown error')}")
    else:
        # No command line arguments - run interactive mode
        interactive_mode()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: Unexpected error: {str(e)}")
        sys.exit(1)