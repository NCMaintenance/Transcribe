import streamlit as st
import requests
import json
from datetime import datetime
import io # For in-memory file handling
from docx import Document # For Word documents
# from docx.shared import Pt # Not strictly needed for basic paragraph/heading
from fpdf import FPDF # For PDF documents

# --- Page Configuration ---
st.set_page_config(
    page_title="Dr. Scribe",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Helper Functions & Constants ---

# Define the expected JSON schema for the Gemini API response (for structured summary)
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

# --- API Call Functions ---
def get_structured_summary_from_gemini(transcript_text):
    """
    Sends the transcript to Gemini API for structured summarization.
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
            "responseSchema": STRUCTURED_SUMMARY_SCHEMA,
        }
    }
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except KeyError:
        return None, "GEMINI_API_KEY not found in st.secrets. Please configure it."
        
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        if (result.get("candidates") and result["candidates"][0].get("content") and
            result["candidates"][0]["content"].get("parts") and result["candidates"][0]["content"]["parts"][0].get("text")):
            json_text = result["candidates"][0]["content"]["parts"][0]["text"]
            try:
                return json.loads(json_text), None
            except json.JSONDecodeError as e:
                st.error(f"Raw AI Response (JSON parse error): {json_text}")
                return None, f"Failed to parse JSON from AI: {e}. Check console for raw response."
        else:
            # Handle cases where the response structure is unexpected or content is missing (e.g. safety blocks)
            error_message = f"Unexpected API response structure. Full response: {result}"
            if result.get("promptFeedback", {}).get("blockReason"):
                error_message = f"Content blocked by API. Reason: {result['promptFeedback']['blockReason']}. Details: {result['promptFeedback'].get('safetyRatings', '')}"
            return None, error_message
    except requests.exceptions.HTTPError as http_err:
        error_detail = f"HTTP error occurred: {http_err}."
        try:
            error_content = http_err.response.json()
            error_detail += f" API Message: {error_content.get('error', {}).get('message', str(error_content))}"
        except ValueError: # If response is not JSON
            error_detail += f" Response: {http_err.response.text}"
        return None, error_detail
    except requests.exceptions.RequestException as e:
        return None, f"API request failed: {e}"
    except Exception as e:
        return None, f"An unexpected error occurred during API call: {e}"


def get_doctors_narrative_summary_from_gemini(transcript_text):
    """
    Sends the transcript to Gemini API for a narrative summary in doctor's terms.
    """
    prompt = f"""
      You are an expert medical AI. Analyze the following doctor's transcript or patient notes.
      Generate a concise, narrative summary of the consultation suitable for a doctor's review.
      The summary should be in prose, use appropriate medical terminology, and highlight clinically relevant information,
      including chief complaint, pertinent history, key examination findings, assessment/diagnosis, and the treatment plan.
      Do NOT use a JSON structure for this summary. Provide a plain text narrative.

      Transcript:
      ---
      {transcript_text}
      ---

      Doctor's Narrative Summary:
    """
    chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
    payload = {"contents": chat_history} # No responseSchema for plain text
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except KeyError:
        return None, "GEMINI_API_KEY not found in st.secrets. Please configure it."

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        if (result.get("candidates") and result["candidates"][0].get("content") and
            result["candidates"][0]["content"].get("parts") and result["candidates"][0]["content"]["parts"][0].get("text")):
            return result["candidates"][0]["content"]["parts"][0]["text"], None
        else:
            error_message = f"Unexpected API response structure for narrative. Full response: {result}"
            if result.get("promptFeedback", {}).get("blockReason"):
                error_message = f"Narrative content blocked by API. Reason: {result['promptFeedback']['blockReason']}. Details: {result['promptFeedback'].get('safetyRatings', '')}"
            return None, error_message
    except requests.exceptions.HTTPError as http_err:
        error_detail = f"HTTP error for narrative summary: {http_err}."
        try:
            error_content = http_err.response.json()
            error_detail += f" API Message: {error_content.get('error', {}).get('message', str(error_content))}"
        except ValueError:
            error_detail += f" Response: {http_err.response.text}"
        return None, error_detail
    except requests.exceptions.RequestException as e:
        return None, f"API request for narrative summary failed: {e}"
    except Exception as e:
        return None, f"An unexpected error occurred during narrative API call: {e}"

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

def create_pdf_from_structured_summary(summary_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    try:
        # Attempt to add DejaVu font. This file must be in the same directory or a full path provided.
        pdf.add_font("DejaVu", "", "DejaVuSansCondensed.ttf", uni=True)
        pdf.set_font("DejaVu", size=10) # Use a font that supports more characters
    except RuntimeError:
        st.warning("DejaVuSansCondensed.ttf font not found. PDF will use a standard font, which may have limited character support. Place the .ttf file in the script's directory.")
        pdf.set_font("Arial", size=10) # Fallback font

    pdf.set_font_size(16)
    pdf.cell(0, 10, 'Structured Medical Summary', ln=True, align='C', border=0) # Removed border for cleaner look
    pdf.ln(5)

    for key in DISPLAY_ORDER:
        value = summary_data.get(key, "Not mentioned or N/A.")
        friendly_name = FRIENDLY_NAMES.get(key, key.replace("([A-Z])", " $1").title())
        
        pdf.set_font_size(12)
        if pdf.font_family == "DejaVu": # Check if custom font was loaded
            pdf.set_font("DejaVu", 'B')
        else:
            pdf.set_font("Arial", 'B') # Fallback bold

        pdf.multi_cell(0, 7, friendly_name, ln=True)
        
        pdf.set_font_size(10)
        if pdf.font_family == "DejaVu":
             pdf.set_font("DejaVu", '')
        else:
            pdf.set_font("Arial", '') # Fallback regular

        pdf.multi_cell(0, 7, str(value) if value else "Not mentioned or N/A.", ln=True)
        pdf.ln(3)
        
    bio = io.BytesIO()
    pdf.output(bio)
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

def create_pdf_from_narrative_summary(narrative_text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    try:
        pdf.add_font("DejaVu", "", "DejaVuSansCondensed.ttf", uni=True)
        pdf.set_font("DejaVu", size=10)
    except RuntimeError:
        # Warning already shown for structured summary, so don't repeat
        pdf.set_font("Arial", size=10)

    pdf.set_font_size(16)
    pdf.cell(0, 10, "Doctor's Narrative Summary", ln=True, align='C', border=0)
    pdf.ln(5)
    pdf.set_font_size(10)
    pdf.multi_cell(0, 7, narrative_text if narrative_text else "No narrative summary generated.", ln=True)
    bio = io.BytesIO()
    pdf.output(bio)
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

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { background: linear-gradient(to bottom right, #1a202c, #2d3748); color: #e2e8f0; }
    h1 { color: #63b3ed; text-align: center; padding-top: 20px; }
    .subtitle { color: #90cdf4; text-align: center; margin-bottom: 30px; }
    .stTextArea textarea { background-color: #2d3748; color: #e2e8f0; border: 1px solid #4a5568; border-radius: 8px; min-height: 200px; }
    .stButton button { background-color: #4299e1; color: white; font-weight: bold; border-radius: 8px; padding: 10px 20px; border: none; transition: background-color 0.2s; }
    .stButton button:hover { background-color: #3182ce; }
    .stButton button:disabled { background-color: #718096; color: #a0aec0; }
    .summary-section h2, .narrative-summary-section h2 { color: #63b3ed; border-bottom: 2px solid #4a5568; padding-bottom: 10px; margin-top: 30px; }
    .summary-item, .narrative-summary-content { background-color: #2d3748; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #4a5568; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    .summary-item h3 { color: #90cdf4; margin-bottom: 8px; font-size: 1.1em; }
    .summary-item p, .narrative-summary-content p { color: #cbd5e0; white-space: pre-wrap; line-height: 1.6; }
    .summary-item .not-mentioned { color: #718096; font-style: italic; }
    .download-buttons-container { margin-top: 10px; margin-bottom:10px; display: flex; gap: 10px; } /* For potential future use if buttons are grouped */
    .footer { text-align: center; margin-top: 40px; padding-bottom: 20px; color: #a0aec0; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)

# --- UI Layout ---
st.markdown("<h1>Dr. Scribe 🩺</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>AI-Powered Medical Transcription Analysis & Summarization</p>", unsafe_allow_html=True)

# Input Section
st.subheader("📝 Enter Transcript or Notes:")
transcript_input = st.text_area(
    label="Paste or type doctor's notes, patient conversation transcript, etc. here...",
    value=st.session_state.transcript_text,
    height=250,
    key="transcript_input_area",
    disabled=st.session_state.is_loading_structured or st.session_state.is_loading_narrative,
    label_visibility="collapsed"
)
# Update session state immediately if text area content changes
if transcript_input != st.session_state.transcript_text:
    st.session_state.transcript_text = transcript_input
    # If user edits transcript, clear previous summaries to avoid confusion
    st.session_state.structured_summary = None
    st.session_state.doctors_narrative_summary = None
    st.session_state.error = None
    # st.rerun() # Optional: uncomment if you want instant clearing on edit

# Analyze Transcript Button
analyze_button_col, _ = st.columns([1, 3]) # Constrain button width
with analyze_button_col:
    if st.button("🔬 Analyze Transcript",
                  disabled=st.session_state.is_loading_structured or st.session_state.is_loading_narrative or not st.session_state.transcript_text.strip(),
                  use_container_width=True):
        st.session_state.error = None # Clear previous errors
        st.session_state.structured_summary = None
        st.session_state.doctors_narrative_summary = None # Clear previous narrative
        st.session_state.is_loading_structured = True
        
        with st.spinner("Generating structured summary..."):
            summary_data, error_data = get_structured_summary_from_gemini(st.session_state.transcript_text)
        
        st.session_state.structured_summary = summary_data
        st.session_state.error = error_data # This will display API or parsing errors
        st.session_state.is_loading_structured = False
        st.rerun()

# Error Display
if st.session_state.error and not st.session_state.is_loading_structured and not st.session_state.is_loading_narrative:
    st.error(f"An error occurred: {st.session_state.error}")

# Structured Summary Display Section
if st.session_state.structured_summary and not st.session_state.is_loading_structured:
    st.markdown("<div class='summary-section'><h2>Structured Summary</h2></div>", unsafe_allow_html=True)
    for key in DISPLAY_ORDER:
        value = st.session_state.structured_summary.get(key)
        if value is not None: # Ensure key exists
            display_name = FRIENDLY_NAMES.get(key, key.replace("([A-Z])", " $1").title())
            st.markdown(f"<div class='summary-item'><h3>{display_name}</h3>", unsafe_allow_html=True)
            if isinstance(value, str) and value.strip() and value.lower() not in ["not mentioned", "n/a", ""]:
                st.markdown(f"<p>{value}</p>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='not-mentioned'>Not mentioned or N/A.</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # Download buttons for Structured Summary
    st.markdown("<h5>Download Structured Summary:</h5>", unsafe_allow_html=True)
    col1, col2, col_spacer = st.columns([1,1,2]) # Adjusted for better spacing
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
    with col2:
        try:
            pdf_structured_data = create_pdf_from_structured_summary(st.session_state.structured_summary)
            st.download_button(
                label="📄 Download as PDF",
                data=pdf_structured_data,
                file_name="structured_summary.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="download_pdf_structured"
            )
        except Exception as e:
            st.error(f"Error generating PDF for structured summary: {e}")
    st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)


    # Generate Doctor's Narrative Summary Button (appears after structured summary)
    narrative_button_col, _ = st.columns([1.5, 2.5]) 
    with narrative_button_col:
        if st.button("🧑‍⚕️ Generate Doctor's Narrative Summary",
                      disabled=st.session_state.is_loading_narrative or not st.session_state.transcript_text.strip(),
                      use_container_width=True, key="generate_narrative_button"):
            st.session_state.error = None # Clear previous errors
            st.session_state.doctors_narrative_summary = None
            st.session_state.is_loading_narrative = True
            
            with st.spinner("Generating doctor's narrative summary..."):
                narrative_data, error_data = get_doctors_narrative_summary_from_gemini(st.session_state.transcript_text)
            
            st.session_state.doctors_narrative_summary = narrative_data
            if error_data: 
                st.session_state.error = error_data # Display narrative-specific error
            st.session_state.is_loading_narrative = False
            st.rerun()

# Doctor's Narrative Summary Display Section
if st.session_state.doctors_narrative_summary and not st.session_state.is_loading_narrative:
    st.markdown("<div class='narrative-summary-section'><h2>Doctor's Narrative Summary</h2></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='narrative-summary-content'><p>{st.session_state.doctors_narrative_summary}</p></div>", unsafe_allow_html=True)

    # Download buttons for Narrative Summary
    st.markdown("<h5>Download Narrative Summary:</h5>", unsafe_allow_html=True)
    col_narr_1, col_narr_2, col_narr_spacer = st.columns([1,1,2])
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
    with col_narr_2:
        try:
            pdf_narrative_data = create_pdf_from_narrative_summary(st.session_state.doctors_narrative_summary)
            st.download_button(
                label="📄 Download as PDF",
                data=pdf_narrative_data,
                file_name="doctors_narrative_summary.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="download_pdf_narrative"
            )
        except Exception as e:
            st.error(f"Error generating PDF for narrative summary: {e}")


# Footer
st.markdown(f"""
<div class='footer'>
    <p>&copy; {datetime.now().year} Dr. Scribe. Powered by Gemini AI.</p>
    <p>Intellectual property belongs to Dave Maher.</p>
    <p>This tool is for informational purposes and should be verified by a medical professional.</p>
    <p style='font-size: 0.8em;'>For PDF generation, ensure 'DejaVuSansCondensed.ttf' is in the script's directory or use a standard font.</p>
</div>
""", unsafe_allow_html=True)

