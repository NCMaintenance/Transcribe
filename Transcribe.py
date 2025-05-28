import streamlit as st
import google.generativeai as genai
import json
import os
from datetime import datetime
from docx import Document
import io
import tempfile
from streamlit_webrtc import webrtc_streamer, WebRtcMode, ClientSettings
import av
import numpy as np
import wave

# --- Streamlit Config ---
st.set_page_config(page_title="Dr. Scribe", layout="wide")

# --- Setup Gemini ---
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# --- Audio Recording (up to 1 hour) ---
st.title("🩺 Dr. Scribe")
st.markdown("### 🎙️ Record Doctor-Patient Interaction")

class AudioRecorder:
    def __init__(self):
        self.frames = []

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        self.frames.append(frame.to_ndarray())
        return frame

    def get_audio_bytes(self):
        if not self.frames:
            return None
        audio_np = np.concatenate(self.frames, axis=1).astype(np.int16)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wf:
            with wave.open(wf.name, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(44100)
                wav_file.writeframes(audio_np.tobytes())
            return wf.name

recorder = AudioRecorder()
ctx = webrtc_streamer(
    key="audio",
    mode=WebRtcMode.SENDONLY,
    client_settings=ClientSettings(media_stream_constraints={"audio": True, "video": False}),
    audio_receiver_size=256,
    sendback_audio=False,
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    audio_frame_callback=recorder.recv,
)

if ctx.state.playing:
    st.success("Recording... Speak now.")
else:
    st.info("Click 'Start' to begin recording.")

if st.button("Stop and Transcribe"):
    audio_path = recorder.get_audio_bytes()
    if audio_path:
        with st.spinner("Transcribing via Gemini..."):
            # Upload & Transcribe
            audio_file = genai.upload_file(path=audio_path)
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            prompt = ("You are a medical transcriptionist. Transcribe the following doctor-patient consultation. "
                      "Label speakers as 'Doctor:' or 'Patient:' when possible.")
            result = model.generate_content([prompt, audio_file], request_options={"timeout": 600})
            genai.delete_file(audio_file.name)
            transcript = result.text
            st.session_state["transcript"] = transcript
            os.remove(audio_path)
    else:
        st.warning("No audio captured.")

# --- Transcript Display ---
if "transcript" in st.session_state:
    st.markdown("## 📄 Transcript")
    st.text_area("Transcription", st.session_state["transcript"], height=300)

    # --- Summarization ---
    if st.button("Analyze Transcript"):
        with st.spinner("Generating summaries with Gemini..."):
            model = genai.GenerativeModel("gemini-1.5-pro-latest")

            # --- Structured Summary ---
            structured_prompt = f"""
You are a medical scribe. Extract key details from this doctor-patient transcript and return JSON with:
- patientName
- dateOfVisit
- chiefComplaint
- historyPresentIllness
- pastMedicalHistory
- medications
- allergies
- reviewOfSystems
- physicalExam
- assessment
- plan
- followUp

If not mentioned, use "Not mentioned".
Transcript:
{st.session_state['transcript']}
            """
            response1 = model.generate_content(structured_prompt)
            structured = json.loads(response1.text)

            # --- Narrative Summary ---
            narrative_prompt = f"""
Summarize the transcript into a coherent, professional doctor’s narrative summary using appropriate medical language.
Transcript:
{st.session_state['transcript']}
            """
            response2 = model.generate_content(narrative_prompt)
            narrative = response2.text

            st.session_state["structured"] = structured
            st.session_state["narrative"] = narrative
            st.success("Summaries generated.")

# --- Results Display ---
if "structured" in st.session_state and "narrative" in st.session_state:
    st.markdown("## 📑 Structured Summary")
    for k, v in st.session_state["structured"].items():
        st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")

    st.download_button("📥 Download Structured Summary (DOCX)",
        data=create_docx(st.session_state["structured"], "structured"),
        file_name="structured_summary.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    st.markdown("---")
    st.markdown("## 🧑‍⚕️ Doctor's Narrative Summary")
    st.write(st.session_state["narrative"])

    st.download_button("📥 Download Narrative Summary (DOCX)",
        data=create_docx(st.session_state["narrative"], "narrative"),
        file_name="narrative_summary.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# --- DOCX Functions ---
def create_docx(content, kind="structured"):
    doc = Document()
    if kind == "structured":
        doc.add_heading("Structured Medical Summary", level=1)
        for key, val in content.items():
            doc.add_heading(key.replace('_', ' ').title(), level=2)
            doc.add_paragraph(val)
    else:
        doc.add_heading("Doctor's Narrative Summary", level=1)
        doc.add_paragraph(content)
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output
