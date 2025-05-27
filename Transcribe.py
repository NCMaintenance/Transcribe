import streamlit as st
import requests
import json
import base64 # For encoding audio data
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Dr. Scribe",
    page_icon="🎙️", # Changed icon
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Helper Functions & Constants ---

# Define the expected JSON schema for the Gemini API response
SUMMARY_SCHEMA = {
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

# Order of keys for display
DISPLAY_ORDER = [
    "patientName", "dateOfVisit", "chiefComplaint", "historyPresentIllness",
    "pastMedicalHistory", "medications", "allergies", "reviewOfSystems",
    "physicalExam", "assessment", "plan", "followUp"
]

# Friendly names for display
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

# Supported audio MIME types for upload and a basic mapping
# Gemini supports more, but these are common for st.file_uploader
# For inline data, Gemini supports WAV, MP3, AIFF, AAC, OGG Vorbis, FLAC.
AUDIO_MIME_TYPES = {
    "audio/wav": "wav",
    "audio/mpeg": "mp3", # Covers mp3
    "audio/ogg": "ogg", # Covers ogg vorbis
    "audio/flac": "flac",
    "audio/aac": "aac",
    "audio/x-m4a": "m4a" # Common for Apple devices
}
# File extensions for the uploader
ACCEPTED_AUDIO_EXTENSIONS = ["wav", "mp3", "ogg", "flac", "aac", "m4a"]


# --- API Call Function ---
def analyze_input_with_gemini(input_content, input_type="text", audio_mime_type=None):
    """
    Sends the input (text or audio) to Gemini API for analysis and structured summarization.
    For audio, it instructs Gemini to first transcribe, then summarize.
    """
    parts = []
    if input_type == "text":
        prompt = f"""
          You are an expert medical scribe. Analyze the following doctor's transcript or patient notes.
          Extract key information and structure it according to the provided JSON schema.
          Focus on accurately capturing medical details for each section.
          If information for a specific section is not present in the transcript, use "Not mentioned" or "N/A" for that field.
          Ensure your response is a valid JSON object matching the schema.

          Transcript:
          ---
          {input_content}
          ---
        """
        parts.append({"text": prompt})
    elif input_type == "audio" and audio_mime_type:
        audio_prompt = """
You are an expert medical scribe. The following audio contains a doctor's consultation or notes.
1. First, accurately transcribe the spoken content in the audio.
2. Then, using the full transcription, analyze the content and extract key information to structure it according to the provided JSON schema.
Focus on accurately capturing medical details for each section of the schema from the transcribed text.
If information for a specific section is not present in the transcribed text, use "Not mentioned" or "N/A" for that field.
Ensure your final output is a single valid JSON object matching the schema, based on the transcribed audio content.
        """
        parts.append({"text": audio_prompt})
        parts.append({
            "inlineData": {
                "mimeType": audio_mime_type,
                "data": input_content # Expecting base64 encoded string here
            }
        })
    else:
        return None, "Invalid input type or missing audio MIME type."

    chat_history = [{"role": "user", "parts": parts}]
    payload = {
        "contents": chat_history,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SUMMARY_SCHEMA,
        }
    }

    api_key = ""  # Gemini API key will be injected by the environment in Canvas
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=180) # Increased timeout for audio
        response.raise_for_status()
        result = response.json()

        if (result.get("candidates") and
            result["candidates"][0].get("content") and
            result["candidates"][0]["content"].get("parts") and
            result["candidates"][0]["content"]["parts"][0].get("text")):
            json_text = result["candidates"][0]["content"]["parts"][0]["text"]
            try:
                parsed_json = json.loads(json_text)
                return parsed_json, None  # Summary, Error
            except json.JSONDecodeError as e:
                st.error(f"Failed to parse JSON response: {e}")
                st.text_area("Raw AI Response (for debugging):", value=json_text, height=150)
                return None, f"Failed to parse the summary from AI: {e}. Raw response: {json_text[:500]}..."
        else:
            error_message = "Received an unexpected response structure from the AI."
            if result.get("promptFeedback") and result["promptFeedback"].get("blockReason"):
                error_message += f" Block Reason: {result['promptFeedback']['blockReason']}."
                if result["promptFeedback"].get("safetyRatings"):
                     error_message += f" Safety Ratings: {result['promptFeedback']['safetyRatings']}"
            st.error(f"Unexpected API response structure: {result}")
            return None, error_message

    except requests.exceptions.HTTPError as http_err:
        error_detail = f"HTTP error occurred: {http_err}."
        try:
            error_content = response.json()
            error_detail += f" Response: {error_content.get('error', {}).get('message', str(error_content))}"
        except ValueError:
            error_detail += f" Response: {response.text}"
        st.error(error_detail)
        return None, error_detail
    except requests.exceptions.RequestException as req_err:
        st.error(f"Request error occurred: {req_err}")
        return None, f"A network or request error occurred: {req_err}"
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return None, f"An unexpected error occurred: {e}"

# --- Initialize Session State ---
if 'transcript_text' not in st.session_state:
    st.session_state.transcript_text = ""
if 'uploaded_audio_file' not in st.session_state:
    st.session_state.uploaded_audio_file = None
if 'summary' not in st.session_state:
    st.session_state.summary = None
if 'error' not in st.session_state:
    st.session_state.error = None
if 'is_loading' not in st.session_state:
    st.session_state.is_loading = False
if 'current_analysis_type' not in st.session_state: # To know what was analyzed
    st.session_state.current_analysis_type = None


# --- Custom CSS for Styling ---
st.markdown("""
<style>
    /* Main container styling */
    .stApp {
        background: linear-gradient(to bottom right, #1a202c, #2d3748);
        color: #e2e8f0;
    }
    /* Header styling */
    h1 {
        color: #63b3ed; /* Sky blue for main title */
        text-align: center;
        padding-top: 20px;
    }
    .subtitle {
        color: #90cdf4; /* Lighter blue for subtitle */
        text-align: center;
        margin-bottom: 20px; /* Reduced margin */
    }
    /* Input sections */
    .stTextArea textarea, .stFileUploader label {
        color: #e2e8f0 !important; /* Ensure text is light */
    }
    .stTextArea textarea {
        background-color: #2d3748;
        border: 1px solid #4a5568;
        border-radius: 8px;
        min-height: 150px; /* Adjusted height */
    }
    .stFileUploader > div > button { /* Style the upload button */
        background-color: #4a5568;
        color: #e2e8f0;
        border-radius: 8px;
    }
    .stFileUploader > div > div > p { /* Style the uploader text "Drag and drop file here" */
        color: #a0aec0 !important;
    }
    /* Button styling */
    .stButton button {
        background-color: #4299e1;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px 20px;
        border: none;
        transition: background-color 0.2s ease-in-out;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    .stButton button:hover {
        background-color: #3182ce;
    }
    .stButton button:disabled {
        background-color: #718096;
        color: #a0aec0;
    }
    /* Summary section styling */
    .summary-section h2 {
        color: #63b3ed;
        border-bottom: 2px solid #4a5568;
        padding-bottom: 10px;
        margin-top: 20px; /* Reduced margin */
    }
    .summary-item {
        background-color: #2d3748;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        border: 1px solid #4a5568;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .summary-item h3 {
        color: #90cdf4;
        margin-bottom: 8px;
        font-size: 1.1em;
    }
    .summary-item p {
        color: #cbd5e0;
        white-space: pre-wrap;
        line-height: 1.6;
    }
    .summary-item .not-mentioned {
        color: #718096;
        font-style: italic;
    }
    /* Footer styling */
    .footer {
        text-align: center;
        margin-top: 30px; /* Reduced margin */
        padding-bottom: 20px;
        color: #a0aec0;
        font-size: 0.9em;
    }
    /* Info/Warning boxes */
    .info-box {
        background-color: #313a4f; /* Darker blue-gray */
        color: #a0aec0;
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        font-size: 0.9em;
        border-left: 4px solid #4299e1; /* Blue accent */
    }
</style>
""", unsafe_allow_html=True)


# --- UI Layout ---
st.markdown("<h1>Dr. Scribe 🎙️</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>AI-Powered Medical Transcription & Analysis</p>", unsafe_allow_html=True)

# Input Method Selection (using columns for better layout)
col1, col2 = st.columns(2)

with col1:
    st.subheader("📝 Option 1: Enter Transcript Text")
    transcript_text_input = st.text_area(
        label="Paste or type doctor's notes, patient conversation transcript, etc. here...",
        value=st.session_state.transcript_text,
        height=200, # Increased height slightly
        key="transcript_text_area",
        disabled=st.session_state.is_loading,
        label_visibility="collapsed"
    )
    # Update session state immediately after input
    st.session_state.transcript_text = transcript_text_input


with col2:
    st.subheader("🎤 Option 2: Upload Audio File")
    uploaded_audio = st.file_uploader(
        "Upload an audio file (e.g., WAV, MP3, OGG, FLAC, AAC, M4A)",
        type=ACCEPTED_AUDIO_EXTENSIONS,
        key="audio_uploader",
        disabled=st.session_state.is_loading,
        accept_multiple_files=False
    )
    # Update session state immediately after upload
    st.session_state.uploaded_audio_file = uploaded_audio

    st.markdown("""
    <div class="info-box">
        <strong>Note on Audio Files:</strong>
        <ul>
            <li>For direct uploads, Gemini API typically supports audio up to <strong>1 minute or ~256KB</strong>.</li>
            <li>Longer audio may require different processing methods not included here.</li>
            <li>Ensure audio is clear for best transcription and analysis.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)


# Action Button - Centered
button_col_spacer1, button_col, button_col_spacer2 = st.columns([1,1.5,1]) # Adjust ratio for centering
with button_col:
    if st.button("✨ Analyze Input", disabled=st.session_state.is_loading, use_container_width=True):
        # Reset previous results
        st.session_state.summary = None
        st.session_state.error = None
        st.session_state.is_loading = True
        st.session_state.current_analysis_type = None

        processed_input = False

        # Prioritize audio file if provided
        if st.session_state.uploaded_audio_file is not None:
            st.session_state.current_analysis_type = "Audio"
            audio_bytes = st.session_state.uploaded_audio_file.getvalue()
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Determine MIME type from file uploader
            uploaded_mime_type = st.session_state.uploaded_audio_file.type
            if uploaded_mime_type not in AUDIO_MIME_TYPES:
                st.session_state.error = f"Unsupported audio file type: {uploaded_mime_type}. Please use one of {', '.join(AUDIO_MIME_TYPES.values())}."
                st.session_state.is_loading = False
            else:
                with st.spinner(f"Analyzing uploaded audio file ({st.session_state.uploaded_audio_file.name})... This may take a moment."):
                    summary_data, error_data = analyze_input_with_gemini(audio_base64, input_type="audio", audio_mime_type=uploaded_mime_type)
                st.session_state.summary = summary_data
                st.session_state.error = error_data
                processed_input = True
        
        # If no audio, or if audio processing failed and user also entered text, process text
        elif st.session_state.transcript_text.strip():
            st.session_state.current_analysis_type = "Text"
            with st.spinner("Analyzing transcript text..."):
                summary_data, error_data = analyze_input_with_gemini(st.session_state.transcript_text, input_type="text")
            st.session_state.summary = summary_data
            st.session_state.error = error_data
            processed_input = True
        
        else: # No input provided
            st.session_state.error = "Please enter a transcript or upload an audio file to analyze."
            processed_input = False

        st.session_state.is_loading = False
        # Clear the uploaded file from session state after processing to avoid re-processing on rerun,
        # but only if it was the source of analysis.
        # Keep text in text_area.
        if st.session_state.current_analysis_type == "Audio":
             st.session_state.uploaded_audio_file = None # This will clear the uploader UI too via key
        
        st.rerun() # Rerun to update UI based on new state


# Error Display
if st.session_state.error and not st.session_state.is_loading: # Only show error if not loading
    st.error(f"An error occurred: {st.session_state.error}")

# Summary Display Section
if st.session_state.summary and not st.session_state.is_loading:
    analysis_source_msg = f" (from {st.session_state.current_analysis_type})" if st.session_state.current_analysis_type else ""
    st.markdown(f"<div class='summary-section'><h2>Structured Summary{analysis_source_msg}</h2></div>", unsafe_allow_html=True)

    for key in DISPLAY_ORDER:
        value = st.session_state.summary.get(key)
        if value is not None:
            display_name = FRIENDLY_NAMES.get(key, key.replace("([A-Z])", " $1").title())
            st.markdown(f"<div class='summary-item'><h3>{display_name}</h3>", unsafe_allow_html=True)
            if isinstance(value, str) and value.strip() and value.lower() not in ["not mentioned", "n/a", ""]:
                st.markdown(f"<p>{value}</p>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='not-mentioned'>Not mentioned or N/A.</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown(f"""
<div class='footer'>
    <p>&copy; {datetime.now().year} Dr. Scribe. Powered by Gemini AI.</p>
    <p>This tool is for informational purposes and should be verified by a medical professional.</p>
</div>
""", unsafe_allow_html=True)

