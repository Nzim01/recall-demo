# Stub implementation for Recall.ai SDK, for demo purposes.
# This file simulates the behavior of RecallClient without external dependencies.

import asyncio

class RecallClient:
    def __init__(self, api_key):
        self.api_key = api_key

    async def create_bot(self, meeting_url, start_time):
        # Simulate bot creation asynchronously
        print(f"Simulating bot creation for meeting: {meeting_url} starting at {start_time}")
        # Create a dummy bot object with an 'id' attribute.
        class Bot:
            pass
        bot = Bot()
        bot.id = "dummy_bot_id"
        # Simulate a short delay
        await asyncio.sleep(1)
        return bot

    async def get_transcript(self, bot_id):
        # Simulate retrieval of transcript asynchronously
        print(f"Fetching transcript for bot: {bot_id}")
        await asyncio.sleep(1)
        return "This is a dummy transcript of the meeting conversation." 