from quart import Quart, request, jsonify, abort
import os
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests
import openai
from datetime import datetime
import hmac
import hashlib

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

latest_article_suggestion = None  # To store the most recent article suggestion

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

def verify_recall_signature(request_data, signature_header):
    """Verify the webhook signature from Recall.ai"""
    webhook_secret = os.getenv('RECALL_WEBHOOK_SECRET')
    if not webhook_secret:
        return True  # Skip verification if no secret is set
        
    computed_signature = hmac.new(
        webhook_secret.encode(),
        request_data,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed_signature, signature_header)

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

# @app.route('/generate-article/<bot_id>', methods=['GET'])
# async def generate_article(bot_id):
#     transcript_data = get_transcript(bot_id)
#     print(f"Transcript data: {transcript_data}")
#     if transcript_data:
#         transcript_text = transcript_data.get('text', '')
#         article = generate_article(transcript_text)
#         return jsonify({'article': article})
#     else:
#         return jsonify({"status": "error", "message": "Failed to retrieve transcript"}), 500

def old_generate_article(transcript):
    print(f"Transcript in generate article: {transcript}")
    # response = openai.Completion.create(
    #     engine="text-davinci-003",
    #     prompt=f"Generate a detailed article based on the following conversation:\n\n{transcript}",
    #     max_tokens=1000
    # )
    # return response.choices[0].text.strip()
    return transcript;

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
        newshookUrl = 'https://newshook-machine-individual-494231981629.us-central1.run.app/api'
        response = requests.post(f'{newshookUrl}/individual/article-suggestion', json=payload)
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
                response = article_suggestion(str(article) + " suggest an article based on the business and prospect summary. the article shouldn't be about the prospect or business directly, but instead aboutthis company and something interesting about the industry and how this company fits into it")
                print(f"Article suggestion response: {response}")
                formated_response = jsonify({'suggestion': response})
                latest_article_suggestion = formated_response  # Store the latest suggestion
                
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(port=5001)
