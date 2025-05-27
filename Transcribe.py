import streamlit as st
from streamlit_js_eval import streamlit_js_eval
import base64
import tempfile
import os
import requests

st.set_page_config(page_title="Dr. Scribe", page_icon="🩺")
st.title("Dr. Scribe - Real-Time Audio Transcription (Gemini)")

API_KEY = st.secrets["GEMINI_API_KEY"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"

st.markdown("Click **Start Recording**, speak, then press **Stop** to transcribe.")

# JS audio recorder
recorder = streamlit_js_eval(js_expressions="navigator.mediaDevices && 'MediaRecorder' in window", key="js_support")

if recorder:
    js_code = """
    let chunks = [];
    let recorder;
    let mediaStream;

    const startRecording = async () => {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(mediaStream);
        chunks = [];

        recorder.ondataavailable = e => chunks.push(e.data);
        recorder.onstop = () => {
            const blob = new Blob(chunks, { type: 'audio/wav' });
            blob.arrayBuffer().then(buffer => {
                const bytes = new Uint8Array(buffer);
                const b64 = btoa(String.fromCharCode(...bytes));
                const data = JSON.stringify({ audio: b64 });
                window.parent.postMessage({ streamlitMessageType: "streamlit:customMessage", data: data }, "*");
            });
        };

        recorder.start();
        window.recorder = recorder;
    };

    const stopRecording = () => {
        if (window.recorder) {
            window.recorder.stop();
            mediaStream.getTracks().forEach(track => track.stop());
        }
    };

    window.startRecording = startRecording;
    window.stopRecording = stopRecording;
    """
    st.components.v1.html(f"<script>{js_code}</script>", height=0)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Recording"):
            streamlit_js_eval(js_expressions="startRecording()", key="start_record")
    with col2:
        if st.button("Stop Recording"):
            streamlit_js_eval(js_expressions="stopRecording()", key="stop_record")

    audio_data = st.experimental_get_query_params().get("audio")
    if audio_data:
        audio_bytes = base64.b64decode(audio_data[0])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        st.audio(audio_bytes, format="audio/wav")
        st.info("Transcribing using Gemini...")

        with open(tmp_path, "rb") as audio_file:
            audio_b64 = base64.b64encode(audio_file.read()).decode("utf-8")

        # Gemini API prompt
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "inline_data": {
                        "mime_type": "audio/wav",
                        "data": audio_b64
                    }
                }]
            }]
        }

        response = requests.post(f"{GEMINI_URL}?key={API_KEY}", headers=headers, json=payload)
        result = response.json()

        if "candidates" in result:
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            st.success("Transcription complete!")
            st.text_area("Transcribed Text", text, height=200)
        else:
            st.error("Transcription failed.")
        os.remove(tmp_path)
else:
    st.error("Browser does not support audio recording.")
