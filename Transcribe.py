import streamlit as st
import os
from pydub import AudioSegment
import speech_recognition as sr
from PIL import Image
from streamlit_audiorecorder import audiorecorder
from streamlit_extras.add_vertical_space import add_vertical_space
from dotenv import load_dotenv

# Load environment variables if using APIs later
load_dotenv()

st.set_page_config(page_title="Audio & Image Uploader", layout="centered")
st.title("Audio and Image Transcription Tool")
add_vertical_space(1)

# === IMAGE UPLOAD ===
st.subheader("Upload an Image")
image_file = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"])
if image_file:
    image = Image.open(image_file)
    st.image(image, caption="Uploaded Image", use_column_width=True)

add_vertical_space(2)

# === AUDIO RECORD OR UPLOAD ===
st.subheader("Record or Upload Audio")

audio_bytes = audiorecorder("Click to record", "Recording...")
uploaded_audio_file = st.file_uploader("Or upload a WAV/MP3 file", type=["wav", "mp3"])

final_audio_path = None

# Save recorded audio
if audio_bytes:
    with open("recorded.wav", "wb") as f:
        f.write(audio_bytes)
    final_audio_path = "recorded.wav"
elif uploaded_audio_file:
    audio_format = uploaded_audio_file.name.split(".")[-1]
    audio = AudioSegment.from_file(uploaded_audio_file, format=audio_format)
    audio.export("uploaded.wav", format="wav")
    final_audio_path = "uploaded.wav"

# === TRANSCRIPTION ===
if final_audio_path:
    recognizer = sr.Recognizer()
    with sr.AudioFile(final_audio_path) as source:
        audio_data = recognizer.record(source)

    try:
        transcript = recognizer.recognize_google(audio_data)
        st.success("Transcription:")
        st.write(transcript)
    except sr.UnknownValueError:
        st.error("Could not understand the audio.")
    except sr.RequestError:
        st.error("Could not request results from Google Speech Recognition service.")

    os.remove(final_audio_path)
