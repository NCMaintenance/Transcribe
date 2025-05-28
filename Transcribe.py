import streamlit as st
import requests
import json
from datetime import datetime
import io
from docx import Document
import os

# --- NEW: Using audio-recorder-streamlit ---
from audio_recorder_streamlit import audio_recorder
import google.generativeai as genai

# --- Page Configuration ---
st.set_page_config(
    page_title="Dr. Scribe",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Helper Functions & Constants ---
STRUCTURED_SUMMARY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
      "patientName": { "type": "STRING", "description": "Patient's full name, if mentioned. Otherwise, 'Not mentioned'." },
      "dateOfVisit": { "type": "STRING", "description": "Date of the visit, if mentioned. Otherwise, 'Not mentioned'." },
      "chiefComplaint": { "type": "STRING", "description": "The main reason for the patient's visit as stated by the patient." },
      "historyPresentIllness": { "type": "STRING", "description": "A detailed chronological account of the development of the patient's current illness." },
      "pastMedicalHistory": { "type": "STRING", "description": "Summary of relevant past illnesses, surgeries, hospitalizations, and allergies." },
      "medications": { "type": "STRING", "description": "List of current medications, including dosage and frequency, if available." },
      "allergies": { "type": "STRING", "description": "List of known allergies and reactions." },
      "reviewOfSystems": { "type": "STRING", "description": "Systematic review of body systems, noting pertinent positives and negatives." },
      "physicalExam": { "type": "STRING", "description": "Key findings from the physical examination, including vital signs if relevant." },
      "assessment": { "type": "STRING", "description": "The doctor's diagnosis or differential diagnoses for the patient's condition." },
      "plan": { "type": "STRING", "description": "The doctor's plan for treatment, including tests, procedures, medications, referrals, and patient education." },
      "followUp": { "type": "STRING", "description": "Instructions for follow-up appointments, further monitoring, or care." }
    },
    "required": [
        "patientName", "dateOfVisit", "chiefComplaint", "historyPresentIllness",
        "pastMedicalHistory", "medications", "allergies", "reviewOfSystems",
        "physicalExam", "assessment", "plan", "followUp"
    ]
}
DISPLAY_ORDER = [
    "patientName", "dateOfVisit", "chiefComplaint", "historyPresentIllness",
    "pastMedicalHistory", "medications", "allergies", "reviewOfSystems",
    "physicalExam", "assessment", "plan", "followUp"
]
FRIENDLY_NAMES = {
    "patientName": "👤 Patient Name",
    "dateOfVisit": "📅 Date of Visit",
    "chiefComplaint": "❓ Chief Complaint",
    "historyPresentIllness": "⏳ History of Present Illness (HPI)",
    "pastMedicalHistory": "📜 Past Medical History (PMH)",
    "medications": "💊 Current Medications",
    "allergies": "⚠️ Allergies",
    "reviewOfSystems": "📋 Review of Systems (ROS)",
    "physicalExam": "🩺 Physical Examination Findings",
    "assessment": "🧠 Assessment / Diagnosis",
    "plan": "📝 Plan",
    "followUp": "➡️ Follow-up Instructions"
}

# --- Transcription & Diarization with Gemini 1.5 Pro ---
def transcribe_with_gemini(audio_path):
    """
    Transcribes an audio file and performs speaker diarization using the Gemini API.
    """
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        audio_file = genai.upload_file(path=audio_path)
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
        prompt = (
            "You are an expert medical transcriptionist. Transcribe the following audio recording "
            "of a doctor-patient consultation. It is critical that you accurately identify and label each speaker. "
            "Use 'Doctor:' and 'Patient:' as the speaker labels if you can distinguish their roles based on context "
            "and vocabulary. Otherwise, use 'Speaker 1:' and 'Speaker 2:'. "
            "Ensure the final transcript is clear, accurate, and well-formatted."
        )
        response = model.generate_content([prompt, audio_file], request_options={"timeout": 600})
        genai.delete_file(audio_file.name)
        return response.text, None
    except Exception as e:
        try:
            if 'audio_file' in locals() and audio_file:
                genai.delete_file(audio_file.name)
        except Exception as cleanup_error:
            st.warning(f"Could not clean up uploaded file: {cleanup_error}")
        return None, f"An error occurred with the Gemini API: {e}"

# --- Gemini API Call Functions for Summaries ---
def get_structured_summary_from_gemini(transcript_text, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    prompt = f"""
      You are an expert medical scribe. Analyze the following doctor's transcript.
      The transcript is labeled with speaker roles.
      Extract key information and structure it according to the provided JSON schema.
      Focus on accurately capturing medical details for each section.
      If information for a specific section is not present, use "Not mentioned".
      Ensure your response is a valid JSON object.

      Transcript:
      ---
      {transcript_text}
      ---
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json", "response_schema": STRUCTURED_SUMMARY_SCHEMA}
        )
        return json.loads(response.text), None
    except Exception as e:
        return None, f"Gemini structured summary error: {e}"

def get_doctors_narrative_summary_from_gemini(transcript_text, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    prompt = f"""
      You are an expert medical AI. Analyze the following doctor's transcript.
      The transcript is labeled with speaker roles.
      Generate a concise, narrative summary of the consultation suitable for a doctor's review.
      The summary should be in prose, use appropriate medical terminology, and highlight clinically relevant information,
      including chief complaint, pertinent history, key examination findings, assessment/diagnosis, and the treatment plan.
      Provide a plain text narrative.

      Transcript:
      ---
      {transcript_text}
      ---

      Doctor's Narrative Summary:
    """
    try:
        response = model.generate_content(prompt)
        return response.text, None
    except Exception as e:
        return None, f"Gemini narrative summary error: {e}"

# --- Download Generation Functions ---
def create_docx_from_structured_summary(summary_data):
    doc = Document()
    doc.add_heading('Structured Medical Summary', level=1)
    for key in DISPLAY_ORDER:
        value = summary_data.get(key, "Not mentioned or N/A.")
        friendly_name = FRIENDLY_NAMES.get(key, key.replace("([A-Z])", " $1").title())
        doc.add_heading(friendly_name, level=2)
        doc.add_paragraph(str(value) if value else "Not mentioned or N/A.")
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()

def create_docx_from_narrative_summary(narrative_text):
    doc = Document()
    doc.add_heading("Doctor's Narrative Summary", level=1)
    doc.add_paragraph(narrative_text if narrative_text else "No narrative summary generated.")
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()

# --- Initialize Session State ---
if 'transcript_text' not in st.session_state:
    st.session_state.transcript_text = ""
if 'structured_summary' not in st.session_state:
    st.session_state.structured_summary = None
if 'doctors_narrative_summary' not in st.session_state:
    st.session_state.doctors_narrative_summary = None
if 'error' not in st.session_state:
    st.session_state.error = None
if 'is_loading_structured' not in st.session_state:
    st.session_state.is_loading_structured = False
if 'is_loading_narrative' not in st.session_state:
    st.session_state.is_loading_narrative = False
if 'is_loading_audio' not in st.session_state:
    st.session_state.is_loading_audio = False

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { background: linear-gradient(to bottom right, #1a202c, #2d3748); color: #e2e8f0; }
    h1 { color: #63b3ed; text-align: center; padding-top: 20px; }
    .subtitle { color: #90cdf4; text-align: center; margin-bottom: 30px; }
    .stTextArea textarea { background-color: #2d3748; color: #e2e8f0; border: 1px solid #4a5568; border-radius: 8px; min-height: 250px; }
    .stButton button { background-color: #4299e1; color: white; font-weight: bold; border-radius: 8px; padding: 10px 20px; border: none; transition: background-color 0.2s; }
    .stButton button:hover { background-color: #3182ce; }
    .stButton button:disabled { background-color: #718096; color: #a0aec0; }
    .summary-section h2, .narrative-summary-section h2 { color: #63b3ed; border-bottom: 2px solid #4a5568; padding-bottom: 10px; margin-top: 30px; }
    .summary-item, .narrative-summary-content { background-color: #2d3748; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #4a5568; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    .summary-item h3 { color: #90cdf4; margin-bottom: 8px; font-size: 1.1em; }
    .summary-item p, .narrative-summary-content p { color: #cbd5e0; white-space: pre-wrap; line-height: 1.6; }
    .summary-item .not-mentioned { color: #718096; font-style: italic; }
    .footer { text-align: center; margin-top: 40px; padding-bottom: 20px; color: #a0aec0; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)

# --- UI Layout ---
st.markdown("<h1>Dr. Scribe 🩺</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>AI-Powered Medical Transcription, Diarization, and Analysis</p>", unsafe_allow_html=True)

# --- Audio Input Section using audio-recorder-streamlit ---
st.markdown("### 🎙️ Option 1: Record Audio Directly")
# You can customize the look and behavior of the recorder
# For example: audio_recorder(text="Click to Record", icon_size="2x", pause_threshold=2.0)
audio_bytes = audio_recorder(
    text="Click the mic to start recording",
    recording_color="#e8b62c", # A gold-like color for recording
    neutral_color="#6aa36f",  # A calm green for idle
    icon_name="microphone",      # Using a more standard microphone icon
    icon_size="3x",
    pause_threshold=2.0,       # Auto-stop after 2s of silence
    sample_rate=44100          # Standard sample rate
)


if audio_bytes and not st.session_state.is_loading_audio: # Check if audio_bytes is not None and not empty
    if st.button("🎤 Transcribe Recording with Gemini"):
        st.session_state.is_loading_audio = True
        st.session_state.error = None
        st.session_state.transcript_text = ""
        st.session_state.structured_summary = None
        st.session_state.doctors_narrative_summary = None

        audio_file_path = "temp_audio.wav"
        with open(audio_file_path, "wb") as f:
            f.write(audio_bytes) # audio_bytes is directly usable

        with st.spinner("Gemini 1.5 Pro is transcribing and identifying speakers... Please wait. ⏳"):
            final_transcript, error = transcribe_with_gemini(audio_file_path)
            if error:
                st.session_state.error = error
            else:
                st.session_state.transcript_text = final_transcript
        
        st.session_state.is_loading_audio = False
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)
        st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# --- Text Input Section ---
st.markdown("### 📝 Option 2: Paste Transcript or Notes")
transcript_input = st.text_area(
    label="Your Gemini-generated transcript will appear here, or you can paste your own text.",
    value=st.session_state.transcript_text,
    height=300,
    key="transcript_input_area",
    disabled=st.session_state.is_loading_structured or st.session_state.is_loading_narrative or st.session_state.is_loading_audio,
    label_visibility="collapsed"
)

if transcript_input != st.session_state.transcript_text:
    st.session_state.transcript_text = transcript_input
    st.session_state.structured_summary = None
    st.session_state.doctors_narrative_summary = None
    st.session_state.error = None

# --- Main Analyze Button ---
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("GEMINI_API_KEY not found in st.secrets. Please add it to continue.")
    st.stop()

analyze_button_col, _ = st.columns([1, 3])
with analyze_button_col:
    if st.button("🔬 Analyze Transcript",
                  disabled=any([st.session_state.is_loading_structured,
                                st.session_state.is_loading_narrative,
                                st.session_state.is_loading_audio,
                                not st.session_state.transcript_text.strip()]),
                  use_container_width=True):
        st.session_state.error = None
        st.session_state.structured_summary = None
        st.session_state.doctors_narrative_summary = None
        st.session_state.is_loading_structured = True

        with st.spinner("Generating structured summary with Gemini..."):
            summary_data, error_data = get_structured_summary_from_gemini(st.session_state.transcript_text, gemini_api_key)

        st.session_state.structured_summary = summary_data
        st.session_state.error = error_data
        st.session_state.is_loading_structured = False
        st.rerun()

# --- Error Display & Results Sections ---
if st.session_state.error and not any([st.session_state.is_loading_structured, st.session_state.is_loading_narrative, st.session_state.is_loading_audio]):
    st.error(f"An error occurred: {st.session_state.error}")

if st.session_state.structured_summary and not st.session_state.is_loading_structured:
    st.markdown("<div class='summary-section'><h2>Structured Summary</h2></div>", unsafe_allow_html=True)
    for key in DISPLAY_ORDER:
        value = st.session_state.structured_summary.get(key)
        if value is not None:
            display_name = FRIENDLY_NAMES.get(key, key.replace("([A-Z])", " $1").title())
            st.markdown(f"<div class='summary-item'><h3>{display_name}</h3>", unsafe_allow_html=True)
            if isinstance(value, str) and value.strip() and value.lower() not in ["not mentioned", "n/a", ""]:
                st.markdown(f"<p>{value}</p>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='not-mentioned'>Not mentioned or N/A.</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<h5>Download Structured Summary:</h5>", unsafe_allow_html=True)
    col1, _ = st.columns([1, 3])
    with col1:
        try:
            docx_structured_data = create_docx_from_structured_summary(st.session_state.structured_summary)
            st.download_button(
                label="📄 Download as DOCX",
                data=docx_structured_data,
                file_name="structured_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="download_docx_structured"
            )
        except Exception as e:
            st.error(f"Error generating DOCX for structured summary: {e}")

    st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

    narrative_button_col, _ = st.columns([1.5, 2.5])
    with narrative_button_col:
        if st.button("🧑‍⚕️ Generate Doctor's Narrative Summary",
                      disabled=st.session_state.is_loading_narrative or not st.session_state.transcript_text.strip(),
                      use_container_width=True, key="generate_narrative_button"):
            st.session_state.error = None
            st.session_state.doctors_narrative_summary = None
            st.session_state.is_loading_narrative = True

            with st.spinner("Generating doctor's narrative summary with Gemini..."):
                narrative_data, error_data = get_doctors_narrative_summary_from_gemini(st.session_state.transcript_text, gemini_api_key)

            st.session_state.doctors_narrative_summary = narrative_data
            if error_data:
                st.session_state.error = error_data
            st.session_state.is_loading_narrative = False
            st.rerun()

if st.session_state.doctors_narrative_summary and not st.session_state.is_loading_narrative:
    st.markdown("<div class='narrative-summary-section'><h2>Doctor's Narrative Summary</h2></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='narrative-summary-content'><p>{st.session_state.doctors_narrative_summary}</p></div>", unsafe_allow_html=True)

    st.markdown("<h5>Download Narrative Summary:</h5>", unsafe_allow_html=True)
    col_narr_1, _ = st.columns([1, 3])
    with col_narr_1:
        try:
            docx_narrative_data = create_docx_from_narrative_summary(st.session_state.doctors_narrative_summary)
            st.download_button(
                label="📄 Download as DOCX",
                data=docx_narrative_data,
                file_name="doctors_narrative_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="download_docx_narrative"
            )
        except Exception as e:
            st.error(f"Error generating DOCX for narrative summary: {e}")

# Footer
st.markdown(f"""
<div class='footer'>
    <p>&copy; {datetime.now().year} Dr. Scribe. Powered entirely by Google Gemini AI.</p>
    <p>This tool is for informational purposes and should be verified by a medical professional.</p>
</div>
""", unsafe_allow_html=True)

