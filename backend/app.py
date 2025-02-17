from quart import Quart, request, jsonify
import os
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests
import openai
from datetime import datetime

load_dotenv()

app = Quart(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']
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

calendar_service = build('calendar', 'v3', credentials=creds)

openai.api_key = os.getenv('OPENAI_API_KEY')

BASE_URL = 'https://us-west-2.recall.ai/api/v1/bot/'  # Corrected URL for Recall.ai

def create_bot(meeting_url):
    url = BASE_URL  # Ensure correct endpoint
    headers = {
        'Authorization': f'Token {os.getenv("RECALL_API_KEY")}',
        'Content-Type': 'application/json'
    }

    # Payload with required parameters
    payload = {
        "meeting_url": meeting_url,  # The meeting URL for the bot to join
        "bot_name": "Meeting Notetaker",  # Optional: Name of the bot
        "transcription_options": {
            "provider": "meeting_captions",  # Specify the transcription provider, adjust if needed
            "recording_mode": "speaker_view"  # Recording mode
        }
    }

    # Log payload for debugging
    print(f"Creating bot with payload: {payload}")

    # Make the API request to create the bot
    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        print("Bot created successfully!")
        return response.json()  # Return the bot details
    else:
        print(f"Error creating bot: {response.text}")
        return None

def schedule_bot_for_event(event_id, meeting_url):
    # Retrieve the API key from the environment
    recall_api_key = os.getenv("RECALL_API_KEY")
    if not recall_api_key:
        raise ValueError("Recall.ai API Key is not set in the environment.")

    url = f'https://us-west-2.recall.ai/api/v2/calendar-events/{event_id}/bot/'
    headers = {
        'Authorization': f'Token {recall_api_key}',
        'Content-Type': 'application/json'
    }

    deduplication_key = f"bot_for_event_{event_id}"

    bot_config = {
        "meeting_url": meeting_url,
        "bot_name": "Meeting Notetaker",
        "transcription_options": {
            "provider": "meeting_captions",
            "recording_mode": "speaker_view"
        }
    }

    payload = {
        "deduplication_key": deduplication_key,
        "bot_config": bot_config
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        print("Bot successfully scheduled!")
        return response.json()
    else:
        print(f"Error scheduling bot: {response.text}")
        print(f"Full Scheduling ErrorResponse: {response.json()}")
        return None


def get_transcript(bot_id):
    url = BASE_URL + f'transcripts/{bot_id}'  
    headers = {
        'Authorization': f'Token {os.getenv("RECALL_API_KEY")}',
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()  
    else:
        print(f"Error retrieving transcript: {response.text}")
        return None

@app.route('/schedule-meeting', methods=['POST'])
async def schedule_meeting():
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

    created_event = calendar_service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1
    ).execute()

    meeting_url = created_event['conferenceData']['entryPoints'][0]['uri']
    event_id = created_event['id']  # Store event ID

    print(f"Meeting URL: {meeting_url}")

    # Create bot
    bot_data = create_bot(meeting_url)

    # Schedule Recall.ai bot for the meeting
    print(f"Bot data: {bot_data}")
    print(f"Event ID: {event_id}")
    print(f"Created event: {created_event}")
    schedule_bot_for_event(event_id, meeting_url)
    # bot_data = schedule_bot_for_event(event_id, meeting_url)
    if bot_data:
        return jsonify({
            'event_id': created_event['id'],
            'bot_id': bot_data['id'],
            'meeting_url': meeting_url
        })
    else:
        return jsonify({"status": "error", "message": "Failed to schedule bot"}), 500

@app.route('/generate-article/<bot_id>', methods=['GET'])
async def generate_article(bot_id):
    transcript_data = get_transcript(bot_id)
    if transcript_data:
        transcript_text = transcript_data.get('text', '')
        article = generate_article(transcript_text)
        return jsonify({'article': article})
    else:
        return jsonify({"status": "error", "message": "Failed to retrieve transcript"}), 500

def generate_article(transcript):
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=f"Generate a detailed article based on the following conversation:\n\n{transcript}",
        max_tokens=1000
    )
    return response.choices[0].text.strip()

if __name__ == '__main__':
    app.run(port=5001)
