import streamlit as st
import base64
import tempfile
import os
import time
import requests

# Gemini API Key
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"  # Replace with your actual key

st.set_page_config(page_title="Dr. Scribe")
st.title("Dr. Scribe - Real-Time Audio Transcription")

# JavaScript Recorder Widget
record_script = """
<script>
let mediaRecorder;
let audioChunks = [];

function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = event => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };
            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64Audio = reader.result.split(',')[1];
                    const input = document.getElementById('audio_data');
                    input.value = base64Audio;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                };
                reader.readAsDataURL(blob);
            };
            mediaRecorder.start();
            document.getElementById("record-status").innerText = "Recording...";
        });
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        document.getElementById("record-status").innerText = "Stopped";
    }
}
</script>

<button onclick="startRecording()">Record</button>
<button onclick="stopRecording()">Stop & Transcribe</button>
<p id="record-status">Idle</p>
<input type="hidden" id="audio_data" name="audio_data" />
"""

# Render JavaScript Recorder
st.components.v1.html(record_script, height=180)

# Receive audio from JS
audio_data = st.text_input("Audio Base64", key="audio_data")

if audio_data:
    st.info("Processing audio...")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio_file:
        temp_audio_file.write(base64.b64decode(audio_data))
        temp_audio_path = temp_audio_file.name

    # Transcribe using Gemini API
    with open(temp_audio_path, "rb") as f:
        audio_bytes = f.read()

    gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    # Encode audio to base64 string to send to Gemini
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {"text": "Transcribe the following audio:"},
                {"inline_data": {
                    "mime_type": "audio/webm",
                    "data": audio_base64
                }}
            ]
        }]
    }

    response = requests.post(gemini_api_url, headers=headers, json=payload)
    if response.status_code == 200:
        result = response.json()
        try:
            transcript = result["candidates"][0]["content"]["parts"][0]["text"]
            st.success("Transcription Complete")
            st.text_area("Transcribed Text", transcript, height=200)
        except Exception:
            st.error("Failed to extract transcription.")
    else:
        st.error(f"Gemini API Error: {response.status_code}")

    os.remove(temp_audio_path)
