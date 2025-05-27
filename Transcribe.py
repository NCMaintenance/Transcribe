import streamlit as st
import requests
import json
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Dr. Scribe",
    page_icon="🩺",
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

# --- API Call Function ---
def analyze_transcript_with_gemini(transcript_text):
    """
    Sends the transcript to Gemini API for analysis and structured summarization.
    """
    prompt = f"""
      You are an expert medical scribe. Analyze the following doctor's transcript or patient notes.
      Extract key information and structure it according to the provided JSON schema.
      Focus on accurately capturing medical details for each section.
      If information for a specific section is not present in the transcript, use "Not mentioned" or "N/A" for that field.
      Ensure your response is a valid JSON object matching the schema.

      Transcript:
      ---
      {transcript_text}
      ---
    """
    chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
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
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=120) # Increased timeout
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
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
            error_content = response.json() # Try to get more details from response
            error_detail += f" Response: {error_content}"
        except ValueError: # If response is not JSON
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
if 'transcript' not in st.session_state:
    st.session_state.transcript = ""
if 'summary' not in st.session_state:
    st.session_state.summary = None
if 'error' not in st.session_state:
    st.session_state.error = None
if 'is_loading' not in st.session_state:
    st.session_state.is_loading = False

# --- Custom CSS for Styling ---
st.markdown("""
<style>
    /* Main container styling */
    .stApp {
        background: linear-gradient(to bottom right, #1a202c, #2d3748); /* Dark gradient background */
        color: #e2e8f0; /* Light text color for contrast */
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
        margin-bottom: 30px;
    }

    /* Text area styling */
    .stTextArea textarea {
        background-color: #2d3748; /* Darker background for text area */
        color: #e2e8f0; /* Light text */
        border: 1px solid #4a5568; /* Subtle border */
        border-radius: 8px;
        min-height: 200px; /* Ensure decent height */
    }

    /* Button styling */
    .stButton button {
        background-color: #4299e1; /* Blue button */
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px 20px;
        border: none;
        transition: background-color 0.2s ease-in-out;
        display: block;
        margin-left: auto;
        margin-right: auto; /* Center button */
    }
    .stButton button:hover {
        background-color: #3182ce; /* Darker blue on hover */
    }
    .stButton button:disabled {
        background-color: #718096; /* Gray out when disabled */
        color: #a0aec0;
    }

    /* Summary section styling */
    .summary-section h2 {
        color: #63b3ed;
        border-bottom: 2px solid #4a5568;
        padding-bottom: 10px;
        margin-top: 30px;
    }
    .summary-item {
        background-color: #2d3748; /* Slightly lighter than main bg */
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        border: 1px solid #4a5568;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .summary-item h3 {
        color: #90cdf4; /* Lighter blue for item titles */
        margin-bottom: 8px;
        font-size: 1.1em;
    }
    .summary-item p {
        color: #cbd5e0; /* Off-white for text */
        white-space: pre-wrap; /* Preserve line breaks */
        line-height: 1.6;
    }
    .summary-item .not-mentioned {
        color: #718096; /* Gray for "Not mentioned" */
        font-style: italic;
    }

    /* Footer styling */
    .footer {
        text-align: center;
        margin-top: 40px;
        padding-bottom: 20px;
        color: #a0aec0; /* Muted color for footer */
        font-size: 0.9em;
    }

    /* Error message styling */
    .stAlert {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# --- UI Layout ---
st.markdown("<h1>Dr. Scribe 🩺</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>AI-Powered Medical Transcription Analysis</p>", unsafe_allow_html=True)

# Input Section
st.subheader("📝 Enter Transcript or Notes:")
transcript_input = st.text_area(
    label="Paste or type doctor's notes, patient conversation transcript, etc. here...",
    value=st.session_state.transcript,
    height=250,
    key="transcript_input_area",
    disabled=st.session_state.is_loading,
    label_visibility="collapsed"
)
st.session_state.transcript = transcript_input # Keep session state updated

# Action Button
analyze_button_col, _ = st.columns([1,3]) # To constrain button width a bit
with analyze_button_col:
    if st.button("🧠 Analyze Transcript", disabled=st.session_state.is_loading, use_container_width=True):
        if not st.session_state.transcript.strip():
            st.session_state.error = "Transcript cannot be empty."
            st.session_state.summary = None
        else:
            st.session_state.is_loading = True
            st.session_state.error = None
            st.session_state.summary = None
            with st.spinner("Analyzing transcript... This may take a moment."):
                summary_data, error_data = analyze_transcript_with_gemini(st.session_state.transcript)
            st.session_state.summary = summary_data
            st.session_state.error = error_data
            st.session_state.is_loading = False
            st.rerun() # Rerun to update UI based on new state

# Error Display
if st.session_state.error:
    st.error(f"An error occurred: {st.session_state.error}")

# Summary Display Section
if st.session_state.summary and not st.session_state.is_loading:
    st.markdown("<div class='summary-section'><h2>Structured Summary</h2></div>", unsafe_allow_html=True)

    for key in DISPLAY_ORDER:
        value = st.session_state.summary.get(key) # Use .get for safety
        if value is not None: # Check if key exists and has a value
            display_name = FRIENDLY_NAMES.get(key, key.replace("([A-Z])", " $1").title())
            st.markdown(f"<div class='summary-item'><h3>{display_name}</h3>", unsafe_allow_html=True)
            if isinstance(value, str) and value.strip() and value.lower() not in ["not mentioned", "n/a", ""]:
                st.markdown(f"<p>{value}</p>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='not-mentioned'>Not mentioned or N/A.</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        # else:
            # If a required key is missing from the response, it might indicate an issue.
            # For now, we just skip it. Could add a warning if a required field is missing.
            # st.warning(f"Data for '{FRIENDLY_NAMES.get(key, key)}' was not found in the response.")


# Footer
st.markdown(f"""
<div class='footer'>
    <p>&copy; {datetime.now().year} Dr. Scribe. Powered by Gemini AI.</p>
    <p>This tool is for informational purposes and should be verified by a medical professional.</p>
</div>
""", unsafe_allow_html=True)

