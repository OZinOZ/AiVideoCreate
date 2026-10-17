
from youtube_transcript_api import YouTubeTranscriptApi
import json

video_id = "rDdoUbCFn24"

try:
    print(f"Attempting to fetch transcript for {video_id} using instance method...")
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=['en', 'zh-Hans'])
    print(f"Transcript fetched. Type: {type(transcript)}")
    
    data = transcript.to_raw_data()
    print(f"Converted to raw data. Type: {type(data)}")
    print(f"First item: {data[0] if data else 'Empty'}")
    
    full_text = " ".join([t['text'] for t in data])
    print(f"Full text length: {len(full_text)}")
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
