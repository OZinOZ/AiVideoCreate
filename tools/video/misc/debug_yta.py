
import sys
import youtube_transcript_api
from youtube_transcript_api import YouTubeTranscriptApi

print(f"Python executable: {sys.executable}")
print(f"youtube_transcript_api file: {youtube_transcript_api.__file__}")
print(f"YouTubeTranscriptApi attributes: {dir(YouTubeTranscriptApi)}")
try:
    print(f"get_transcript: {YouTubeTranscriptApi.get_transcript}")
except AttributeError as e:
    print(f"Error accessing get_transcript: {e}")
