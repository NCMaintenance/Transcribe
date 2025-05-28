import streamlit as st
import google.generativeai as genai
import json
import os
from datetime import datetime
from docx import Document
import io
import tempfile

# --- Set up Gemini API ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-pro-latest")

st.set_page_config(page_title="Dr. Scribe", layout="wide")
st.title("🩺 Dr. Scribe")
st.markdown("### 📤 Upload Doctor-Patient Audio")

# --- Upload Audio File ---
uploaded_audio = st.file_uploader("Upload an audio file (WAV, MP3, M4A)", type=["wav", "mp3", "m4a"])

if uploaded_audio:
    st.audio(uploaded_audio, format="audio/wav")

    if st.button("🧠 Transcribe & Analyze"):
        with st.spinner("Processing with Gemini..."):

            # Save audio to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(uploaded_audio.read())
                tmp_file_path = tmp_file.name

            # Upload to Gemini
            audio_file = genai.upload_file(path=tmp_file_path)

            # --- Transcription Prompt ---
            prompt = ("You are a medical transcriptionist. Transcribe the following doctor-patient consultation. "
                      "Label speakers as 'Doctor:' or 'Patient:' when possible.")
            result = model.generate_content([prompt, audio_file], request_options={"timeout": 600})
            transcript = result.text
            genai.delete_file(audio_file.name)
            os.remove(tmp_file_path)

            st.session_state["transcript"] = transcript
            st.success("Transcript generated!")

# --- Show Transcript ---
if "transcript" in st.session_state:
    st.markdown("## 📄 Transcript")
    st.text_area("Transcript", st.session_state["transcript"], height=300)

    if st.button("📊 Summarize Transcript"):
        with st.spinner("Generating structured and narrative summaries..."):

            # --- Structured Summary ---
            prompt_structured = f"""
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
            response1 = model.generate_content(prompt_structured)
            structured = json.loads(response1.text)

            # --- Narrative Summary ---
            prompt_narrative = f"""
Summarize the transcript into a coherent, professional doctor’s narrative summary using appropriate medical language.
Transcript:
{st.session_state['transcript']}
            """
            response2 = model.generate_content(prompt_narrative)
            narrative = response2.text

            st.session_state["structured"] = structured
            st.session_state["narrative"] = narrative
            st.success("Summaries ready.")

# --- Display Summaries ---
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
