import streamlit as st
import base64
import tempfile
import os
import requests # Make sure 'requests' is installed: pip install requests

# --- Configuration ---
# IMPORTANT: Replace "YOUR_GEMINI_API_KEY_HERE" with your actual Gemini API key.
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

st.set_page_config(page_title="Dr. Scribe Enhanced", layout="wide")
st.title("Dr. Scribe - Enhanced Transcription & Note Analysis")
st.markdown("""
Welcome to Dr. Scribe! This tool helps you:
1.  Record audio and get it transcribed by Gemini.
2.  Format the transcript into a structured doctor's note.
3.  Upload patient letters or notes (text files) and extract key information.

**Remember to replace `YOUR_GEMINI_API_KEY_HERE` in the script with your actual Gemini API key.**
""")

# --- Helper Function for Gemini API Calls ---
def call_gemini_api(payload):
    """
    Calls the Gemini API with the given payload.
    Returns the JSON response or None if an error occurs.
    """
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        st.error("CRITICAL: Gemini API Key is not set. Please update the script.")
        return None

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status() # Raises an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Gemini API Request Error: {e}")
        if response is not None:
            st.error(f"Response content: {response.text}")
        return None

def extract_text_from_gemini_response(result):
    """
    Safely extracts text from Gemini API response.
    """
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        st.error(f"Failed to extract text from Gemini response: {e}")
        st.json(result) # Show the problematic response
        return None

# --- JavaScript Recorder Widget ---
# This widget allows recording audio in the browser.
record_script = """
<script>
let mediaRecorder;
let audioChunks = [];
let stream; // Keep track of the stream to stop it

async function startRecording() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' }); // Explicitly set mimeType
        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = () => {
            const blob = new Blob(audioChunks, { type: 'audio/webm' }); // Ensure correct blob type
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64Audio = reader.result.split(',')[1];
                // Send data to Streamlit
                const input = document.getElementById('audio_data_input');
                if (input) {
                    input.value = base64Audio;
                    // Manually trigger Streamlit's input handling
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    console.error('Audio data input element not found');
                }
            };
            reader.readAsDataURL(blob);
            // Stop microphone tracks
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
        };

        mediaRecorder.start();
        document.getElementById("record-status").innerText = "Recording... Click 'Stop & Process' when done.";
        document.getElementById("start-record-btn").disabled = true;
        document.getElementById("stop-record-btn").disabled = false;
    } catch (err) {
        console.error("Error starting recording:", err);
        document.getElementById("record-status").innerText = "Error: Could not start recording. Check microphone permissions.";
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        document.getElementById("record-status").innerText = "Processing audio...";
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
}
</script>

<div style="padding: 10px; border: 1px solid #ddd; border-radius: 5px; text-align: center;">
    <h4>Record Patient Notes</h4>
    <button id="start-record-btn" onclick="startRecording()" style="padding: 10px 15px; margin-right: 10px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer;">Start Recording</button>
    <button id="stop-record-btn" onclick="stopRecording()" style="padding: 10px 15px; background-color: #f44336; color: white; border: none; border-radius: 5px; cursor: pointer;" disabled>Stop & Process Audio</button>
    <p id="record-status" style="margin-top: 10px;">Idle</p>
    <input type="hidden" id="audio_data_input" />
</div>
"""
st.components.v1.html(record_script, height=180)

# Hidden text input to receive audio data from JavaScript
# The key must match what JavaScript targets if we were to use st.text_input directly for updates
# However, with the custom event dispatch, st.session_state is more robust.
if 'audio_data' not in st.session_state:
    st.session_state.audio_data = ""

audio_data_base64 = st.text_input("Audio Base64 (hidden, updated by JS)", key="audio_data_input_key", label_visibility="collapsed")

# Process audio when audio_data_base64 (from JS) has a new value
if audio_data_base64 and audio_data_base64 != st.session_state.get('last_processed_audio_data', ''):
    st.session_state.last_processed_audio_data = audio_data_base64
    st.session_state.raw_transcript = "" # Reset previous transcripts
    st.session_state.formatted_transcript = ""

    st.info("Audio received. Processing...")

    # 1. Transcribe Audio using Gemini
    with st.spinner("Transcribing audio with Gemini..."):
        audio_payload = {
            "contents": [{
                "parts": [
                    {"text": "Transcribe the following audio from a medical context accurately and clearly. Focus on medical terminology if present."},
                    {"inline_data": {
                        "mime_type": "audio/webm", # Matching JS recorder
                        "data": audio_data_base64
                    }}
                ]
            }]
        }
        transcription_result = call_gemini_api(audio_payload)

    if transcription_result:
        raw_transcript = extract_text_from_gemini_response(transcription_result)
        if raw_transcript:
            st.session_state.raw_transcript = raw_transcript
            st.subheader("Raw Transcription")
            st.text_area("Raw Transcript", raw_transcript, height=150, key="raw_trans_text_area")

            # 2. Format Transcript using Gemini
            with st.spinner("Formatting transcript into Doctor's Note style..."):
                formatting_prompt = (
                    "Format the following raw medical transcript into a structured doctor's note. "
                    "Use clear headings such as 'PATIENT IDENTIFICATION', 'CHIEF COMPLAINT (CC)', 'HISTORY OF PRESENT ILLNESS (HPI)', "
                    "'PAST MEDICAL HISTORY (PMH)', 'MEDICATIONS', 'ALLERGIES', 'SOCIAL HISTORY (SH)', 'FAMILY HISTORY (FH)', "
                    "'REVIEW OF SYSTEMS (ROS)', 'PHYSICAL EXAMINATION (PE)', 'ASSESSMENT (A)', and 'PLAN (P)'. "
                    "If information for a specific section is not clearly present in the transcript, you can state 'Not discussed', 'N/A', or omit the heading. "
                    "Ensure the output is well-organized and easy to read.\n\n"
                    "Raw Transcript:\n"
                    f"{raw_transcript}"
                )
                formatting_payload = {
                    "contents": [{"parts": [{"text": formatting_prompt}]}]
                }
                formatting_result = call_gemini_api(formatting_payload)

            if formatting_result:
                formatted_transcript = extract_text_from_gemini_response(formatting_result)
                if formatted_transcript:
                    st.session_state.formatted_transcript = formatted_transcript
                    st.subheader("Formatted Doctor's Note")
                    st.text_area("Formatted Note", formatted_transcript, height=300, key="fmt_trans_text_area")
                else:
                    st.error("Could not extract formatted transcript from Gemini response.")
            else:
                st.error("Failed to get a formatting response from Gemini.")
        else:
            st.error("Could not extract raw transcript from Gemini response.")
    else:
        st.error("Failed to get a transcription response from Gemini.")

    # Clear the hidden input to prevent re-processing on page refresh without new audio
    # This is tricky with st.text_input; using session state to manage flow is better.
    # st.experimental_rerun() # Could be used, but let's rely on state for now.

# Display existing transcripts if available in session state (e.g., after other interactions)
if st.session_state.get('raw_transcript'):
    if not audio_data_base64 or audio_data_base64 != st.session_state.get('last_processed_audio_data', ''):
        st.subheader("Previous Raw Transcription")
        st.text_area("Raw Transcript", st.session_state.raw_transcript, height=150, key="prev_raw_trans_text_area")
if st.session_state.get('formatted_transcript'):
     if not audio_data_base64 or audio_data_base64 != st.session_state.get('last_processed_audio_data', ''):
        st.subheader("Previous Formatted Doctor's Note")
        st.text_area("Formatted Note", st.session_state.formatted_transcript, height=300, key="prev_fmt_trans_text_area")


st.divider()

# --- Letter Analysis Section ---
st.header("Analyze Uploaded Letter/Notes")
st.markdown("Upload a text file (.txt, .md) containing patient letters or existing doctor's notes to extract key information.")

uploaded_file = st.file_uploader("Choose a file", type=['txt', 'md'], key="file_uploader")

if uploaded_file is not None:
    try:
        letter_text = uploaded_file.read().decode()
        st.info(f"File '{uploaded_file.name}' uploaded successfully.")

        with st.expander("View Uploaded Letter Content (First 500 characters)", expanded=False):
            st.text(letter_text[:500] + "..." if len(letter_text) > 500 else letter_text)

        if st.button("Extract Information from Letter", key="extract_letter_btn"):
            with st.spinner("Analyzing letter with Gemini..."):
                extraction_prompt = (
                    "Analyze the following uploaded medical letter/note. Extract key information and present it in a structured format. "
                    "Identify and list: \n"
                    "1. PATIENT DETAILS: Any mention of patient name, date of birth (DOB), age, gender, contact information, patient identifiers.\n"
                    "2. REFERRING DOCTOR/CLINIC (if applicable): Name and contact if mentioned.\n"
                    "3. DATE OF LETTER/NOTE: The date the document was created.\n"
                    "4. CHIEF COMPLAINT/REASON FOR REFERRAL: The main reason for the note or visit.\n"
                    "5. KEY MEDICAL HISTORY: Significant past illnesses, conditions, surgeries.\n"
                    "6. CURRENT MEDICATIONS & ALLERGIES (if mentioned).\n"
                    "7. SUMMARY OF ASSESSMENT/FINDINGS: Key observations, diagnoses, or conclusions from the note.\n"
                    "8. RECOMMENDED PLAN/ACTIONS: Any treatments, follow-ups, or recommendations.\n\n"
                    "If specific information is not found, indicate 'Not found' or 'N/A' for that section. "
                    "Focus on clarity and organization.\n\n"
                    "Letter Content:\n"
                    f"{letter_text}"
                )
                extraction_payload = {
                    "contents": [{"parts": [{"text": extraction_prompt}]}]
                }
                extraction_result = call_gemini_api(extraction_payload)

            if extraction_result:
                extracted_info = extract_text_from_gemini_response(extraction_result)
                if extracted_info:
                    st.subheader("Extracted Information from Letter")
                    st.text_area("Extracted Details", extracted_info, height=400, key="extracted_letter_info_area")
                else:
                    st.error("Could not extract information from Gemini response for the letter.")
            else:
                st.error("Failed to get a response from Gemini for letter analysis.")
    except Exception as e:
        st.error(f"Error processing uploaded file: {e}")

st.markdown("---")
st.markdown("Developed with Gemini & Streamlit.")

# To run this app:
# 1. Save as a Python file (e.g., dr_scribe_app.py)
# 2. Install Streamlit: pip install streamlit requests
# 3. Run from your terminal: streamlit run dr_scribe_app.py
# 4. IMPORTANT: Replace "YOUR_GEMINI_API_KEY_HERE" in the script with your actual Gemini API key.
