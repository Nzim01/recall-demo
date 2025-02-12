from google_auth_oauthlib.flow import Flow
import os

class CalendarService:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        self.credentials = None

    def create_oauth_flow(self):
        # Use the downloaded credentials.json file instead of environment variables.
        flow = Flow.from_client_secrets_file(
            'credentials.json',  # Ensure this file exists and is valid.
            scopes=self.scopes,
            redirect_uri=os.getenv("GOOGLE_REDIRECT_URI")
        )
        return flow

    async def create_meeting(self, title, start_time, end_time, attendees):
        from googleapiclient.discovery import build
        service = build('calendar', 'v3', credentials=self.credentials)
        
        event = {
            'summary': title,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': [{'email': email} for email in attendees],
            'conferenceData': {
                'createRequest': {
                    'requestId': f"meeting_{start_time.timestamp()}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }
        }
        
        event = service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1
        ).execute()
        
        return event 