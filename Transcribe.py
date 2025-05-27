import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, ClientSettings
import av
import whisper
import numpy as np
import queue
import tempfile
import os
import wave

st.title("Real-Time Audio Transcription")

model = whisper.load_model("base")

audio_queue = queue.Queue()

# Define audio processor class
class AudioProcessor:
    def __init__(self):
        self.frames = []

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        audio = frame.to_ndarray().flatten().astype(np.int16)
        audio_queue.put(audio.tobytes())
        return frame

# WebRTC settings
webrtc_streamer(
    key="audio",
    mode=WebRtcMode.SENDONLY,
    in_audio=True,
    audio_processor_factory=AudioProcessor,
    client_settings=ClientSettings(
        media_stream_constraints={"video": False, "audio": True},
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    )
)

# Button to trigger transcription
if st.button("Transcribe"):
    st.info("Processing audio...")

    # Write audio to temp WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wf = wave.open(f, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)

        while not audio_queue.empty():
            wf.writeframes(audio_queue.get())
        wf.close()
        audio_path = f.name

    # Transcribe with Whisper
    result = model.transcribe(audio_path)
    st.success("Transcription complete!")
    st.text_area("Transcribed Text:", result["text"], height=200)

    # Clean up
    os.remove(audio_path)
