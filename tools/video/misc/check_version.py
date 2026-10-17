try:
    import youtube_transcript_api
    from youtube_transcript_api import YouTubeTranscriptApi
    
    with open("d:/AIGen/Script/version_info_utf8.txt", "w", encoding="utf-8") as f:
        f.write(f"Version: {youtube_transcript_api.__version__}\n")
        f.write(f"File: {youtube_transcript_api.__file__}\n")
        f.write(f"Attributes: {dir(YouTubeTranscriptApi)}\n")
        try:
             f.write(f"get_transcript exists: {hasattr(YouTubeTranscriptApi, 'get_transcript')}\n")
        except:
             f.write("get_transcript check failed\n")

except Exception as e:
    with open("d:/AIGen/Script/version_info_utf8.txt", "w", encoding="utf-8") as f:
        f.write(f"Error: {e}\n")
