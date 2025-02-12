from recall_sdk import RecallClient
import os

class RecallService:
    def __init__(self):
        self.client = RecallClient(api_key=os.getenv("RECALL_AI_API_KEY"))
    
    async def schedule_bot(self, meeting_url, start_time):
        """Schedule a bot to join the meeting"""
        bot = await self.client.create_bot(
            meeting_url=meeting_url,
            start_time=start_time
        )
        return bot.id
    
    async def get_transcript(self, bot_id):
        """Get the transcript once the meeting is complete"""
        transcript = await self.client.get_transcript(bot_id)
        return transcript 