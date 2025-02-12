from quart import Quart, request, redirect, jsonify
from calendar_service import CalendarService
from recall_service import RecallService
from article_generator import ArticleGenerator
import os
from datetime import datetime

app = Quart(__name__)
calendar_service = CalendarService()
recall_service = RecallService()
article_generator = ArticleGenerator()

@app.route('/oauth2callback')
async def oauth2callback():
    flow = calendar_service.create_oauth_flow()
    flow.fetch_token(authorization_response=request.url)
    calendar_service.credentials = flow.credentials
    return "Authentication successful!"

@app.route('/schedule-meeting', methods=['POST'])
async def schedule_meeting():
    data = await request.get_json()
    
    # Create calendar event
    start_time = datetime.fromisoformat(data['start_time'])
    end_time = datetime.fromisoformat(data['end_time'])
    
    event = await calendar_service.create_meeting(
        data['title'],
        start_time,
        end_time,
        data['attendees']
    )
    
    # Schedule Recall.ai bot
    bot_id = await recall_service.schedule_bot(
        event['conferenceData']['entryPoints'][0]['uri'],
        start_time
    )
    
    return jsonify({
        'event_id': event['id'],
        'bot_id': bot_id,
        'meeting_url': event['conferenceData']['entryPoints'][0]['uri']
    })

@app.route('/generate-article/<bot_id>')
async def generate_article(bot_id):
    transcript = await recall_service.get_transcript(bot_id)
    article = await article_generator.generate_article(transcript)
    return jsonify({'article': article})

if __name__ == '__main__':
    app.run(debug=True) 