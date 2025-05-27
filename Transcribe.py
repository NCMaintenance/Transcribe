import streamlit as st
import base64
import requests # Make sure 'requests' is installed: pip install requests
import io # For handling byte streams for PDF/Image

# For PDF processing, user needs to install: pip install pdfplumber
import pdfplumber
# Pillow (PIL) might be needed by st.image or if doing image manipulations,
# often a Streamlit dependency. pip install Pillow

# --- Configuration ---
# Attempt to get API key from Streamlit secrets
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except (KeyError, AttributeError): # AttributeError if st.secrets is not defined (e.g. local run without secrets file)
    GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE" # Fallback for local development

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

st.set_page_config(page_title="Dr. Scribe Enhanced", layout="wide")
st.title("Dr. Scribe - Enhanced Transcription & Note Analysis")
st.markdown("""
Welcome to Dr. Scribe! This tool helps you:
1.  Record audio and get it transcribed by Gemini.
2.  Format the transcript into a structured doctor's note.
3.  Upload patient letters or notes (text, PDF, or image files) and extract key information.

**Note:**
- For this app to function, a Gemini API Key is required.
  - If running on Streamlit Community Cloud, set it as `GEMINI_API_KEY` in your app's secrets.
  - If running locally and not using a secrets file, replace `YOUR_GEMINI_API_KEY_HERE` in the script.
- For PDF processing, ensure `pdfplumber` is installed (`pip install pdfplumber`).
""")

# --- Helper Function for Gemini API Calls ---
def call_gemini_api(payload):
    """
    Calls the Gemini API with the given payload.
    Returns the JSON response or None if an error occurs.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        st.error("CRITICAL: Gemini API Key is not set. Please configure it in Streamlit secrets (GEMINI_API_KEY) or update the script.")
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
        if hasattr(response, 'text'):
            st.error(f"Response content: {response.text}")
        return None

def extract_text_from_gemini_response(result):
    """
    Safely extracts text from Gemini API response.
    """
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        st.error(f"Failed to extract text from Gemini response: {e}")
        st.json(result) # Show the problematic response
        return None

# --- JavaScript Recorder Widget ---
record_script = """
<script>
let mediaRecorder;
let audioChunks = [];
let stream; // Keep track of the stream to stop it

async function startRecording() {
    try {
        document.getElementById("record-status").innerText = "Initializing microphone...";
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
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
                const input = document.getElementById('audio_data_input'); // Target by ID
                if (input) {
                    input.value = base64Audio;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    console.error('Audio data input element not found');
                    document.getElementById("record-status").innerText = "Error: Could not send audio data.";
                }
            };
            reader.readAsDataURL(blob);
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
        let errorMsg = "Error: Could not start recording.";
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
            errorMsg += " Please grant microphone permissions.";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
            errorMsg += " No microphone found.";
        }
        document.getElementById("record-status").innerText = errorMsg;
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        document.getElementById("record-status").innerText = "Processing audio...";
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    } else {
        // Handle case where stop is clicked without active recording
        document.getElementById("record-status").innerText = "Idle. Click 'Start Recording'.";
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
}
// Initialize button states on load
window.onload = () => {
    if (document.getElementById("start-record-btn")) {
         document.getElementById("start-record-btn").disabled = false;
    }
    if (document.getElementById("stop-record-btn")) {
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
# The `key` here is for Streamlit's widget identification. JS targets the `id` attribute.
audio_data_base64_from_js = st.text_input("Audio Base64 (hidden, updated by JS)", key="audio_data_input_streamlit_key", label_visibility="collapsed")

# Process audio when new audio data is received from JavaScript
if audio_data_base64_from_js and audio_data_base64_from_js != st.session_state.get('last_processed_audio_data', ''):
    st.session_state.last_processed_audio_data = audio_data_base64_from_js
    st.session_state.raw_transcript = "" # Reset previous transcripts
    st.session_state.formatted_transcript = ""

    st.info("Audio received. Processing...")

    with st.spinner("Transcribing audio with Gemini..."):
        audio_payload = {
            "contents": [{
                "parts": [
                    {"text": "Transcribe the following audio from a medical context accurately and clearly. Focus on medical terminology if present."},
                    {"inline_data": {
                        "mime_type": "audio/webm",
                        "data": audio_data_base64_from_js
                    }}
                ]
            }]
        }
        transcription_result = call_gemini_api(audio_payload)

    if transcription_result:
        raw_transcript = extract_text_from_gemini_response(transcription_result)
        if raw_transcript:
            st.session_state.raw_transcript = raw_transcript
            # Displaying new transcript immediately
            st.subheader("Current Raw Transcription")
            st.text_area("Raw Transcript", raw_transcript, height=150, key="current_raw_trans_text_area")

            with st.spinner("Formatting transcript into Doctor's Note style..."):
                formatting_prompt = (
                    "Format the following raw medical transcript into a structured doctor's note. "
                    "Use clear headings such as 'PATIENT IDENTIFICATION', 'CHIEF COMPLAINT (CC)', 'HISTORY OF PRESENT ILLNESS (HPI)', "
                    "'PAST MEDICAL HISTORY (PMH)', 'MEDICATIONS', 'ALLERGIES', 'SOCIAL HISTORY (SH)', 'FAMILY HISTORY (FH)', "
                    "'REVIEW OF SYSTEMS (ROS)', 'PHYSICAL EXAMINATION (PE)', 'ASSESSMENT (A)', and 'PLAN (P)'. "
                    "If information for a specific section is not clearly present in the transcript, state 'Not discussed' or 'N/A', or omit the heading. "
                    "Ensure the output is well-organized and easy to read.\n\n"
                    "Raw Transcript:\n"
                    f"{raw_transcript}"
                )
                formatting_payload = {"contents": [{"parts": [{"text": formatting_prompt}]}]}
                formatting_result = call_gemini_api(formatting_payload)

            if formatting_result:
                formatted_transcript = extract_text_from_gemini_response(formatting_result)
                if formatted_transcript:
                    st.session_state.formatted_transcript = formatted_transcript
                    st.subheader("Current Formatted Doctor's Note")
                    st.text_area("Formatted Note", formatted_transcript, height=300, key="current_fmt_trans_text_area")
                else:
                    st.error("Could not extract formatted transcript from Gemini response.")
            else:
                st.error("Failed to get a formatting response from Gemini.")
        else:
            st.error("Could not extract raw transcript from Gemini response.")
    else:
        st.error("Failed to get a transcription response from Gemini.")
    # No need to clear audio_data_base64_from_js, its change triggers this block.
    # The st.session_state['last_processed_audio_data'] prevents re-processing.

# Display existing transcripts if they are in session state and no new audio is being processed
elif not audio_data_base64_from_js and st.session_state.get('raw_transcript'): # Show if no new audio and old exists
    st.subheader("Previous Raw Transcription")
    st.text_area("Raw Transcript", st.session_state.raw_transcript, height=150, key="prev_raw_trans_text_area_stale")
    if st.session_state.get('formatted_transcript'):
        st.subheader("Previous Formatted Doctor's Note")
        st.text_area("Formatted Note", st.session_state.formatted_transcript, height=300, key="prev_fmt_trans_text_area_stale")


st.divider()

# --- Letter Analysis Section ---
st.header("Analyze Uploaded Letter/Notes")
st.markdown("Upload a text file (.txt, .md), PDF (.pdf), or image (.png, .jpg, .jpeg) containing patient letters or notes.")

uploaded_file = st.file_uploader(
    "Choose a file",
    type=['txt', 'md', 'pdf', 'png', 'jpg', 'jpeg'],
    key="file_uploader"
)

if uploaded_file is not None:
    st.info(f"File '{uploaded_file.name}' (Type: {uploaded_file.type}) uploaded successfully.")
    extracted_text_from_file = None
    image_base64_for_gemini = None
    file_mime_type_for_gemini = uploaded_file.type # Store the original mime type

    try:
        if uploaded_file.type == "application/pdf":
            with st.spinner("Extracting text from PDF..."):
                try:
                    # Use io.BytesIO to treat byte stream from uploader as a file-like object
                    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
                        pages_text = [page.extract_text() for page in pdf.pages if page.extract_text() is not None]
                    extracted_text_from_file = "\n".join(pages_text)
                    if not extracted_text_from_file.strip():
                        st.warning("No text could be extracted from this PDF. It might be an image-based PDF or empty.")
                        # Future enhancement: Offer to OCR the PDF if text extraction fails.
                        # For now, we could try sending it as an image if it's small enough, or page by page.
                        # This example will just report no text.
                except Exception as e:
                    st.error(f"Error processing PDF: {e}")
                    st.exception(e) # Provides more detail for debugging
                    extracted_text_from_file = None

        elif uploaded_file.type in ["image/png", "image/jpeg", "image/jpg"]:
            with st.spinner("Preparing image for analysis..."):
                image_bytes = uploaded_file.getvalue()
                image_base64_for_gemini = base64.b64encode(image_bytes).decode()
                st.image(image_bytes, caption="Uploaded Image", use_column_width=True)

        elif uploaded_file.type in ["text/plain", "text/markdown"]:
             extracted_text_from_file = uploaded_file.read().decode()
        else: # Fallback for other types that might be text-like
             try:
                extracted_text_from_file = uploaded_file.read().decode()
                st.warning(f"Processed file type '{uploaded_file.type}' as plain text. Results may vary if this is incorrect.")
             except Exception: # Broad except as we don't know the encoding
                st.error(f"Could not read file type '{uploaded_file.type}' as text. Please upload a supported format.")

        if extracted_text_from_file:
            with st.expander("View Extracted Text (First 1000 characters)", expanded=False):
                st.text(extracted_text_from_file[:1000] + "..." if len(extracted_text_from_file) > 1000 else extracted_text_from_file)

        if st.button("Extract Information from Uploaded File", key="extract_file_btn"):
            analysis_result_text = None
            if extracted_text_from_file:
                with st.spinner("Analyzing extracted text with Gemini..."):
                    extraction_prompt = (
                        "Analyze the following medical text. Extract key information and present it in a structured format. "
                        "Identify and list: \n"
                        "1. PATIENT DETAILS: Patient name, date of birth (DOB), age, gender, contact information, patient identifiers.\n"
                        "2. REFERRING DOCTOR/CLINIC (if applicable): Name and contact if mentioned.\n"
                        "3. DATE OF DOCUMENT: The date the document was created.\n"
                        "4. CHIEF COMPLAINT/REASON FOR DOCUMENT: The main reason for the note or visit.\n"
                        "5. KEY MEDICAL HISTORY: Significant past illnesses, conditions, surgeries.\n"
                        "6. CURRENT MEDICATIONS & ALLERGIES (if mentioned).\n"
                        "7. SUMMARY OF ASSESSMENT/FINDINGS: Key observations, diagnoses, or conclusions from the note.\n"
                        "8. RECOMMENDED PLAN/ACTIONS: Any treatments, follow-ups, or recommendations.\n\n"
                        "If specific information is not found, indicate 'Not found' or 'N/A' for that section. "
                        "Focus on clarity and organization.\n\n"
                        "Document Content:\n"
                        f"{extracted_text_from_file}"
                    )
                    analysis_payload = {"contents": [{"parts": [{"text": extraction_prompt}]}]}
                    analysis_result_json = call_gemini_api(analysis_payload)
                    if analysis_result_json:
                        analysis_result_text = extract_text_from_gemini_response(analysis_result_json)

            elif image_base64_for_gemini:
                with st.spinner("Analyzing image with Gemini... (This may take a moment)"):
                    image_analysis_prompt = (
                        "You are an AI assistant specialized in extracting information from medical documents presented as images. "
                        "Analyze the following image of a medical letter or note. First, perform Optical Character Recognition (OCR) to read all visible text. "
                        "Then, based on the recognized text, extract key information and present it in a structured format. "
                        "Identify and list: \n"
                        "1. PATIENT DETAILS: Patient name, DOB, age, gender, contact, identifiers.\n"
                        "2. REFERRING DOCTOR/CLINIC.\n"
                        "3. DATE OF DOCUMENT.\n"
                        "4. CHIEF COMPLAINT/REASON FOR DOCUMENT.\n"
                        "5. KEY MEDICAL HISTORY.\n"
                        "6. CURRENT MEDICATIONS & ALLERGIES.\n"
                        "7. SUMMARY OF ASSESSMENT/FINDINGS.\n"
                        "8. RECOMMENDED PLAN/ACTIONS.\n\n"
                        "If text is unclear or unreadable in parts of the image, note this. "
                        "If specific information is not found, indicate 'Not found' or 'N/A'. "
                        "Output should be well-organized.\n\n"
                        "Begin analysis of the provided image."
                    )
                    analysis_payload = {
                        "contents": [{
                            "parts": [
                                {"text": image_analysis_prompt},
                                {"inline_data": {
                                    "mime_type": file_mime_type_for_gemini, # Use original mime type
                                    "data": image_base64_for_gemini
                                }}
                            ]
                        }]
                    }
                    analysis_result_json = call_gemini_api(analysis_payload)
                    if analysis_result_json:
                        analysis_result_text = extract_text_from_gemini_response(analysis_result_json)
            else:
                st.warning("No content (text or image) available to analyze. Please upload a valid file and ensure text could be extracted if it's a PDF.")

            if analysis_result_text:
                st.subheader("Extracted Information from File")
                st.text_area("Extracted Details", analysis_result_text, height=400, key="extracted_file_info_area")
            elif extracted_text_from_file or image_base64_for_gemini: # Only show if we attempted analysis
                st.error("Failed to get a response from Gemini for file analysis, or no text was extracted from the response.")

    except Exception as e:
        st.error(f"An unexpected error occurred while processing the uploaded file: {e}")
        st.exception(e) # Show full traceback for debugging

st.markdown("---")
st.markdown("Developed with Gemini & Streamlit.")

# To run this app:
# 1. Save as a Python file (e.g., dr_scribe_app.py)
# 2. Install dependencies: pip install streamlit requests pdfplumber Pillow
# 3. Run from your terminal: streamlit run dr_scribe_app.py
# 4. Configure GEMINI_API_KEY in Streamlit secrets or directly in the script if running locally without secrets.
