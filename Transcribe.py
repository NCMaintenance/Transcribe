import streamlit as st
import base64
import io
import tempfile
import os
import wave
import numpy as np
#from pydub import AudioSegment
import whisper

from streamlit_js_eval import streamlit_js_eval
import streamlit.components.v1 as components

st.set_page_config(page_title="Dr. Scribe", layout="centered")
st.title("Dr. Scribe: Audio Transcription")

# Load Whisper model
model = whisper.load_model("base")

# JS/HTML Audio Recorder with start and stop buttons
st.markdown("### Record Audio")

components.html("""
    <div>
        <button onclick="startRecording()">Start Recording</button>
        <button onclick="stopRecording()">Stop Recording</button>
        <p id="status">Status: Idle</p>
    </div>
    <script>
        let recorder;
        let audioChunks;

        async function startRecording() {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            recorder = new MediaRecorder(stream);
            audioChunks = [];

            recorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };

            recorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = function () {
                    const base64Audio = reader.result.split(',')[1];
                    window.parent.postMessage({ type: 'streamlit:setComponentValue', value: base64Audio }, '*');
                    document.getElementById("status").innerText = "Status: Audio sent.";
                };
            };

            recorder.start();
            document.getElementById("status").innerText = "Status: Recording...";
        }

        function stopRecording() {
            recorder.stop();
            document.getElementById("status").innerText = "Status: Stopped";
        }
    </script>
""", height=150)

# Receive audio from JS recorder
audio_base64 = streamlit_js_eval(js_expressions="", key="audio_blob")

if audio_base64:
    audio_bytes = base64.b64decode(audio_base64)
    audio_io = io.BytesIO(audio_bytes)

    # Save audio to a WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        audio_path = f.name

    st.audio(audio_io.read(), format="audio/wav")

    # Transcription
    st.info("Transcribing...")
    result = model.transcribe(audio_path)
    st.success("Transcription complete!")

    st.text_area("Transcribed Text:", result["text"], height=250)

    os.remove(audio_path)
