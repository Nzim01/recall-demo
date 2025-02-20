"""
Meeting Scheduler and Transcription Service
Handles meeting scheduling, bot creation, and transcript processing using Google Calendar and Recall.ai
"""

from datetime import datetime
import hashlib
import hmac
import os

import openai
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from quart import Quart, request, jsonify, abort

# Configuration Constants
SCOPES = ['https://www.googleapis.com/auth/calendar']
RECALL_BASE_URL = 'https://us-west-2.recall.ai/api/v1/bot/'
RECALL_CALENDAR_URL = 'https://us-west-2.recall.ai/api/v2/calendar-events/'
BOT_NAME = "Meeting Notetaker"

# Article Suggestion Constants
NEWSHOOK_URL = 'https://newshook-machine-individual-494231981629.us-central1.run.app/api'
ARTICLE_SUGGESTION_PROMPT = "suggest an article based on the business and prospect summary. the article shouldn't be about the prospect or business directly, but instead about this company and something interesting about the industry and how this company fits into it"

# Load environment variables
load_dotenv()

app = Quart(__name__)

# Initialize credentials and services
def initialize_google_credentials():
    """Initialize and return Google Calendar credentials."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.getenv('GOOGLE_CREDENTIALS_PATH'), SCOPES
            )
            creds = flow.run_local_server(port=5001)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return creds

# Initialize services
creds = initialize_google_credentials()
calendar_service = build('calendar', 'v3', credentials=creds)
openai.api_key = os.getenv('OPENAI_API_KEY')

# Global state
latest_article_suggestion = None

def create_bot(meeting_url: str) -> dict:
    """Create a Recall.ai bot for meeting transcription."""
    headers = {
        'Authorization': f'Token {os.getenv("RECALL_API_KEY")}',
        'Content-Type': 'application/json'
    }

    payload = {
        "meeting_url": meeting_url,
        "bot_name": BOT_NAME,
        "transcription_options": {
            "provider": "meeting_captions",
            "recording_mode": "speaker_view"
        }
    }

    try:
        response = requests.post(RECALL_BASE_URL, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating bot: {str(e)}")
        return None

def schedule_bot_for_event(event_id: str, meeting_url: str) -> dict:
    """Schedule a Recall.ai bot for a specific calendar event."""
    recall_api_key = os.getenv("RECALL_API_KEY")
    if not recall_api_key:
        raise ValueError("Recall.ai API Key is not set in the environment.")

    headers = {
        'Authorization': f'Token {recall_api_key}',
        'Content-Type': 'application/json'
    }

    payload = {
        "deduplication_key": f"bot_for_event_{event_id}",
        "bot_config": {
            "meeting_url": meeting_url,
            "bot_name": BOT_NAME,
            "transcription_options": {
                "provider": "meeting_captions",
                "recording_mode": "speaker_view"
            }
        }
    }

    try:
        response = requests.post(
            f'{RECALL_CALENDAR_URL}{event_id}/bot/',
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error scheduling bot: {str(e)}")
        print(f"Full Scheduling ErrorResponse: {response.json()}")
        return None

def get_transcript(bot_id):
    url = f'https://us-west-2.recall.ai/api/v1/bot/{bot_id}/transcript/'

    headers = {
        'Authorization': f'Token {os.getenv("RECALL_API_KEY")}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    response = requests.get(url, headers=headers)
    print(f"Transcript response: {response.json()}")
    if response.status_code == 200:
        return response.json()  
    else:
        print(f"Error retrieving transcript: {response.text}")
        return None

@app.route('/schedule-meeting', methods=['POST'])
async def schedule_meeting():
    """Handle meeting scheduling and bot creation."""
    try:
        data = await request.get_json()

        # Google Calendar event creation
        start_time = datetime.fromisoformat(data['start_time'])
        end_time = datetime.fromisoformat(data['end_time'])

        event = {
            'summary': data['title'],
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
            'attendees': [{'email': email} for email in data['attendees']],
            'conferenceData': {
                'createRequest': {
                    'requestId': f"meeting_{start_time.timestamp()}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }
        }
        
        # Create calendar event directly
        created_event = calendar_service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1
        ).execute()

        meeting_url = created_event['conferenceData']['entryPoints'][0]['uri']
        event_id = created_event['id']

        # Create and schedule bot
        bot_data = create_bot(meeting_url)
        if not bot_data:
            return jsonify({
                "status": "error",
                "message": "Failed to create bot"
            }), 500

        schedule_bot_for_event(event_id, meeting_url)
        
        return jsonify({
            'event_id': event_id,
            'bot_id': bot_data['id'],
            'meeting_url': meeting_url
        })

    except Exception as e:
        print(f"Error scheduling meeting: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to schedule meeting"
        }), 500

def generate_article(transcript_data):
    print(f"Transcript in generate article: {transcript_data}")
    
    # Combine all words from all speakers into a single text
    full_transcript = ""
    for segment in transcript_data:
        speaker = segment['speaker']
        words = ' '.join(word['text'] for word in segment['words'])
        full_transcript += f"{speaker}: {words}\n"
    
    # For now, just return the formatted transcript
    # In production, you would use OpenAI or another service to generate an article
    return full_transcript

def article_suggestion(source_information):
    try:
        payload = {'source_information': source_information}
        response = requests.post(f'{NEWSHOOK_URL}/individual/article-suggestion', json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': 'Failed to get article suggestion', 'status_code': response.status_code}
    except Exception as e:
        return str(e)

@app.route('/get-latest-suggestion', methods=['GET'])
async def get_latest_suggestion():
    global latest_article_suggestion
    if latest_article_suggestion:
        return jsonify({'suggestion': latest_article_suggestion})
    return jsonify({'suggestion': None}), 404

@app.route('/webhook/recall', methods=['POST'])
async def recall_webhook():
    global latest_article_suggestion
    data = await request.get_json()
    print(f"Received webhook data: {data}")
    
    if data.get('event') == 'bot.status_change':
        bot_data = data.get('data', {})
        bot_id = bot_data.get('bot_id')
        status = bot_data.get('status', {})
        status_code = status.get('code')
        
        print(f"Bot {bot_id} status changed to: {status_code}")
        
        if status_code == 'done':
            transcript_data = get_transcript(bot_id)
            print(f"Transcript in recall webhook: {transcript_data}")
            if transcript_data:
                # Pass the entire transcript_data to generate_article
                article = generate_article(transcript_data)
                print(f"Generated article for bot {bot_id}: {article}")
                response = article_suggestion(str(article) + " " + ARTICLE_SUGGESTION_PROMPT)
                print(f"Article suggestion response: {response}")
                latest_article_suggestion = response  # Store the latest suggestion
                
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(port=5001)
