import streamlit as st
import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()  

BACKEND_URL = os.getenv('BACKEND_URL')

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
            
            # Store bot_id for later article generation
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
            
    # Add separate button for revealing suggestion
    if st.button("Reveal Suggestion"):
        suggestion_response = requests.get(f"{BACKEND_URL}/get-latest-suggestion")
        if suggestion_response.status_code == 200:
            suggestion_data = suggestion_response.json()
            if suggestion_data.get('suggestion'):
                st.subheader("Article Suggestion")
                st.write(suggestion_data['suggestion'])
        else:
            st.warning("No article suggestion available yet.") 
