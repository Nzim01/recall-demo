import streamlit as st
import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()
BACKEND_URL = os.getenv('BACKEND_URL')
SCOPES = ['https://www.googleapis.com/auth/calendar']

def check_google_auth():
    """Check if user is authenticated with Google"""
    try:
        # First check session state
        if 'google_creds' not in st.session_state:
            # If not in session, check if backend has stored credentials
            response = requests.get(f"{BACKEND_URL}/check-auth")
            if response.status_code == 200:
                st.session_state.google_creds = response.json()
                return True
            return False
        
        # Verify existing session credentials
        creds = Credentials.from_authorized_user_info(st.session_state.google_creds, SCOPES)
        if not creds or not creds.valid:
            del st.session_state.google_creds
            return False
        
        # Verify we can actually access the calendar
        try:
            service = build('calendar', 'v3', credentials=creds)
            service.calendarList().list(maxResults=1).execute()
            return True
        except Exception:
            if 'google_creds' in st.session_state:
                del st.session_state.google_creds
            return False
            
    except Exception:
        if 'google_creds' in st.session_state:
            del st.session_state.google_creds
        return False

def google_auth():
    """Handle Google Authentication"""
    flow = InstalledAppFlow.from_client_secrets_file(
        os.getenv('GOOGLE_CREDENTIALS_PATH'),
        SCOPES
    )
    creds = flow.run_local_server(
        port=0,
        authorization_prompt_message='Please login with Google',
        success_message='Authentication successful! You may close this tab.'
    )
    
    # Store credentials in session state
    st.session_state.google_creds = eval(creds.to_json())
    
    # Send credentials to backend
    response = requests.post(
        f"{BACKEND_URL}/store-credentials",
        json=st.session_state.google_creds
    )
    if response.status_code != 200:
        st.error("Failed to store credentials")
        return False
    return True

def show_meeting_scheduler():
    """Show the meeting scheduler interface"""
    st.title("Meeting Scheduler")
    
    with st.form("meeting_scheduler"):
        title = st.text_input("Meeting Title")
        date = st.date_input("Meeting Date")
        time = st.time_input("Meeting Time")
        duration = st.number_input("Duration (minutes)", min_value=15, value=30)
        attendees = st.text_area("Attendees (one email per line)")
        
        submitted = st.form_submit_button("Schedule Meeting")
        
        if submitted:
            start_time = datetime.combine(date, time)
            end_time = start_time + timedelta(minutes=duration)
            
            response = requests.post(
                f"{BACKEND_URL}/schedule-meeting",
                json={
                    'title': title,
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'attendees': [email.strip() for email in attendees.split('\n') if email.strip()]
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                st.success(f"Meeting scheduled successfully!")
                st.write(f"Meeting URL: {data['meeting_url']}")
                st.session_state['bot_id'] = data['bot_id']
            else:
                st.error("Failed to schedule meeting")

    if 'bot_id' in st.session_state:
        if st.button("Generate Article"):
            response = requests.get(f"{BACKEND_URL}/generate-article/{st.session_state['bot_id']}")
            if response.status_code == 200:
                st.write(response.json()['article'])
            else:
                st.error("Failed to generate article")
                
        if st.button("Reveal Suggestion"):
            suggestion_response = requests.get(f"{BACKEND_URL}/get-latest-suggestion")
            if suggestion_response.status_code == 200:
                suggestion_data = suggestion_response.json()
                if suggestion_data.get('suggestion'):
                    st.subheader("Article Suggestion")
                    st.write(suggestion_data['suggestion'])
            else:
                st.warning("No article suggestion available yet.")

def main():
    # Check authentication
    if not check_google_auth():
        st.title("Welcome to Meeting Scheduler")
        st.write("Please login with Google to continue")
        if st.button("Login with Google"):
            if google_auth():
                st.success("Successfully authenticated!")
                st.rerun()  # Rerun the app to show the scheduler
            else:
                st.error("Authentication failed")
    else:
        show_meeting_scheduler()

if __name__ == "__main__":
    main() 
