import streamlit as st
import base64
import requests
import io
import pdfplumber

# --- Configuration ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
API_KEY_SOURCE = "Streamlit Secrets" if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE" else "Placeholder"

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

st.set_page_config(page_title="Dr. Scribe Enhanced", layout="wide")
st.title("Dr. Scribe - Enhanced Transcription & Note Analysis")

# --- Initialize Session State ---
for k, v in [
    ("raw_transcript", ""),
    ("formatted_transcript", ""),
    ("last_processed_audio_data", ""),
    ("extracted_file_info", ""),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# --- API Key Check and Main App Intro ---
if API_KEY_SOURCE == "Streamlit Secrets":
    st.sidebar.success("Gemini API Key loaded successfully from Streamlit Secrets.")
else:
    st.sidebar.warning(f"Gemini API Key: {API_KEY_SOURCE}. Update placeholder if needed.")

if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
    st.error("🔴 CRITICAL: Gemini API Key is not configured or is still the placeholder. The application will not function correctly.")
    st.markdown("""
    **To fix this:**
    - **Streamlit Community Cloud:** Set `GEMINI_API_KEY` in your app's secrets in the Streamlit Cloud dashboard.
    - **Locally:**  
      1. Create `.streamlit/secrets.toml` in your app's root directory.
      2. Add: `GEMINI_API_KEY = "your_actual_api_key_value"`
    """)
    st.stop()

st.markdown("""
Welcome to Dr. Scribe! This tool helps you:
1.  Record audio and get it transcribed by Gemini.
2.  Format the transcript into a structured doctor's note.
3.  Upload patient letters or notes (text, PDF, or image files) and extract key information.

**Important Notes:**
- For PDF processing, ensure `pdfplumber` is installed (`pip install pdfplumber`).
- Ensure microphone permissions are granted in your browser for audio recording.
""")

# --- Helper Function for Gemini API Calls ---
def call_gemini_api(payload):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        st.error("Gemini API Key is missing or is a placeholder. Cannot make API call.")
        return None

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Gemini API Request Error: {e}")
        response_text = ""
        if 'response' in locals() and response is not None and hasattr(response, 'text'):
            response_text = response.text
        elif hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'text'):
            response_text = e.response.text
        if response_text:
            st.error(f"Response content: {response_text}")
        return None

def extract_text_from_gemini_response(result):
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        st.error(f"Failed to extract text from Gemini response: {e}")
        st.json(result)
        return None

# --- JavaScript Recorder Widget with postMessage for Streamlit ---
record_script = """
<script>
let mediaRecorder;
let audioChunks = [];
let stream;

async function startRecording() {
    try {
        document.getElementById("record-status").innerText = "Initializing microphone...";
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        audioChunks = [];
        mediaRecorder.ondataavailable = event => { if (event.data.size > 0) audioChunks.push(event.data); };
        mediaRecorder.onstop = () => {
            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            const reader = new FileReader();
            reader.onloadend = () => {
                let base64Audio = "";
                if (reader.result) {
                    const parts = reader.result.toString().split(',');
                    if (parts.length > 1) base64Audio = parts[1];
                }
                // Send to Streamlit via postMessage:
                window.parent.postMessage({ isStreamlitMessage: true, type: "streamlit:setComponentValue", value: base64Audio }, "*");
                document.getElementById("record-status").innerText = "Idle. Click 'Start Recording'.";
            };
            reader.onerror = () => {
                document.getElementById("record-status").innerText = "Error: Could not read audio data.";
                window.parent.postMessage({ isStreamlitMessage: true, type: "streamlit:setComponentValue", value: "" }, "*");
            };
            if (blob.size > 0) {
                reader.readAsDataURL(blob);
            } else {
                document.getElementById("record-status").innerText = "Warning: Recording was empty or too short.";
                window.parent.postMessage({ isStreamlitMessage: true, type: "streamlit:setComponentValue", value: "" }, "*");
            }
            if (stream) stream.getTracks().forEach(track => track.stop());
        };
        mediaRecorder.start();
        document.getElementById("record-status").innerText = "Recording... Click 'Stop & Process' when done.";
        document.getElementById("start-record-btn").disabled = true;
        document.getElementById("stop-record-btn").disabled = false;
    } catch (err) {
        let errorMsg = "Error: Could not start recording.";
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
            errorMsg += " Please grant microphone permissions.";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
            errorMsg += " No microphone found.";
        } else if (err.name === "NotReadableError") {
            errorMsg += " Microphone is already in use.";
        }
        document.getElementById("record-status").innerText = errorMsg;
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    } else {
        document.getElementById("record-status").innerText = "Idle. Click 'Start Recording'.";
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
}

window.onload = () => {
    const startBtn = document.getElementById("start-record-btn");
    const stopBtn = document.getElementById("stop-record-btn");
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
    const status = document.getElementById("record-status");
    if (status) status.innerText = "Idle. Click 'Start Recording'.";
};
</script>

<div style="padding: 10px; border: 1px solid #ddd; border-radius: 5px; text-align: center; margin-bottom: 20px;">
    <h4>Record Patient Notes</h4>
    <p style="font-size: 0.9em; color: #555;">Ensure your microphone is enabled and permissions are granted in your browser.</p>
    <button id="start-record-btn" onclick="startRecording()" style="padding: 10px 15px; margin: 5px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer;">Start Recording</button>
    <button id="stop-record-btn" onclick="stopRecording()" style="padding: 10px 15px; margin: 5px; background-color: #f44336; color: white; border: none; border-radius: 5px; cursor: pointer;" disabled>Stop & Process Audio</button>
    <p id="record-status" style="margin-top: 10px; font-weight: bold;">Idle</p>
</div>
"""
audio_data_base64_from_js = st.components.v1.html(record_script, height=220)

# --- Audio Processing Logic ---
if audio_data_base64_from_js and audio_data_base64_from_js != st.session_state.last_processed_audio_data:
    st.session_state.last_processed_audio_data = audio_data_base64_from_js

    proceed_with_api_call = False
    # Defensive: Handle any type for audio_data_base64_from_js before using len()
    is_valid_audio_string = isinstance(audio_data_base64_from_js, str)
    audio_length = len(audio_data_base64_from_js) if is_valid_audio_string else 0

    if not audio_data_base64_from_js:
        st.warning("Received empty audio data. Please try recording again.")
        st.session_state.raw_transcript = "Error: Received empty audio data from recorder."
        st.session_state.formatted_transcript = ""
    elif not is_valid_audio_string or \
         audio_data_base64_from_js.lower() == "undefined" or \
         audio_length < 100:
        st.error(f"Audio data appears invalid or too short (length {audio_length}). Please try again.")
        st.session_state.raw_transcript = "Error: Invalid or too short audio data received from recorder."
        st.session_state.formatted_transcript = ""
    else:
        proceed_with_api_call = True

    if proceed_with_api_call:
        if audio_length < 500:
            st.warning(f"Recorded audio is quite short (data length: {audio_length} characters). Transcription quality may be affected.")
        st.info("New audio data received. Processing...")
        with st.spinner("Transcribing audio with Gemini..."):
            audio_payload = {
                "contents": [{
                    "parts": [
                        {"text": "Transcribe the following audio from a medical context accurately and clearly. Focus on medical terminology if present. Ensure the transcription is verbatim."},
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
                with st.spinner("Formatting transcript into Doctor's Note style..."):
                    formatting_prompt = (
                        "Format the following raw medical transcript into a structured doctor's note. "
                        "Use clear headings such as 'PATIENT IDENTIFICATION', 'CHIEF COMPLAINT (CC)', 'HISTORY OF PRESENT ILLNESS (HPI)', "
                        "'PAST MEDICAL HISTORY (PMH)', 'MEDICATIONS', 'ALLERGIES', 'SOCIAL HISTORY (SH)', 'FAMILY HISTORY (FH)', "
                        "'REVIEW OF SYSTEMS (ROS)', 'PHYSICAL EXAMINATION (PE)', 'ASSESSMENT (A)', and 'PLAN (P)'. "
                        "If information for a specific section is not clearly present in the transcript, state 'Not discussed' or 'N/A', or omit the heading. "
                        "Ensure the output is well-organized, professional, and easy to read.\n\n"
                        "Raw Transcript:\n"
                        f"{st.session_state.raw_transcript}"
                    )
                    formatting_payload = {"contents": [{"parts": [{"text": formatting_prompt}]}]}
                    formatting_result = call_gemini_api(formatting_payload)
                if formatting_result:
                    formatted_transcript = extract_text_from_gemini_response(formatting_result)
                    if formatted_transcript:
                        st.session_state.formatted_transcript = formatted_transcript
                    else:
                        st.error("Could not extract formatted transcript from Gemini response.")
                        st.session_state.formatted_transcript = "Error: Formatting failed."
                else:
                    st.error("Failed to get a formatting response from Gemini.")
                    st.session_state.formatted_transcript = "Error: No formatting response from Gemini."
            else:
                st.error("Could not extract raw transcript from Gemini response.")
                st.session_state.raw_transcript = "Error: Transcription failed."
                st.session_state.formatted_transcript = ""
        else:
            st.error("Failed to get a transcription response from Gemini.")
            st.session_state.raw_transcript = "Error: No transcription response from Gemini API."
            st.session_state.formatted_transcript = ""

# --- Display Last Processed Audio Transcripts ---
if st.session_state.raw_transcript:
    st.subheader("Last Processed Audio Transcription")
    st.text_area("Raw Transcript", st.session_state.raw_transcript, height=150, key="displayed_raw_transcript")
    if st.session_state.formatted_transcript:
        st.subheader("Formatted Doctor's Note from Audio")
        st.text_area("Formatted Note", st.session_state.formatted_transcript, height=300, key="displayed_formatted_transcript")
    elif st.session_state.raw_transcript and not st.session_state.raw_transcript.startswith("Error:"):
        st.warning("Raw transcript is available, but formatting failed, is pending, or resulted in an error.")

st.divider()

# --- Letter Analysis Section ---
st.header("Analyze Uploaded Letter/Notes")
st.markdown("""
Upload a text file (.txt, .md), PDF (.pdf), or image (.png, .jpg, .jpeg) containing patient letters or notes.
- **PDFs:** Text-based PDFs work best. Encrypted or image-only PDFs may not yield text.
- **Images:** Clear, high-resolution images provide better analysis.
""")

uploaded_file = st.file_uploader(
    "Choose a file",
    type=['txt', 'md', 'pdf', 'png', 'jpg', 'jpeg'],
    key="file_uploader"
)

if uploaded_file is not None:
    st.info(f"File '{uploaded_file.name}' (Type: {uploaded_file.type}) uploaded successfully.")
    extracted_text_from_file = None
    image_base64_for_gemini = None
    file_mime_type_for_gemini = uploaded_file.type

    try:
        if uploaded_file.type == "application/pdf":
            with st.spinner("Extracting text from PDF..."):
                try:
                    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
                        pages_text = [page.extract_text() for page in pdf.pages if page.extract_text() is not None]
                    extracted_text_from_file = "\n".join(pages_text)
                    if not extracted_text_from_file.strip():
                        st.warning("No text could be extracted from this PDF. It might be an image-based PDF, encrypted, or empty.")
                        extracted_text_from_file = None
                except Exception as e:
                    st.error(f"Error processing PDF: {e}. The PDF might be encrypted or corrupted.")
                    st.exception(e)
                    extracted_text_from_file = None

        elif uploaded_file.type in ["image/png", "image/jpeg", "image/jpg"]:
            with st.spinner("Preparing image for analysis..."):
                image_bytes = uploaded_file.getvalue()
                image_base64_for_gemini = base64.b64encode(image_bytes).decode()
                st.image(image_bytes, caption="Uploaded Image", use_column_width=True)

        elif uploaded_file.type in ["text/plain", "text/markdown"]:
            extracted_text_from_file = uploaded_file.read().decode()
        else:
            try:
                extracted_text_from_file = uploaded_file.read().decode()
                st.warning(f"Processed file type '{uploaded_file.type}' as plain text. Results may vary.")
            except Exception:
                st.error(f"Could not read file type '{uploaded_file.type}' as text. Please upload a supported format.")

        if extracted_text_from_file:
            with st.expander("View Extracted Text (First 1000 characters)", expanded=False):
                st.text(extracted_text_from_file[:1000] + "..." if len(extracted_text_from_file) > 1000 else extracted_text_from_file)

        if st.button("Extract Information from Uploaded File", key="extract_file_btn"):
            st.session_state.extracted_file_info = ""
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
                                    "mime_type": file_mime_type_for_gemini,
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
                st.session_state.extracted_file_info = analysis_result_text
            elif extracted_text_from_file or image_base64_for_gemini:
                st.error("Failed to get a response from Gemini for file analysis, or no text was extracted from the response.")
                st.session_state.extracted_file_info = "Error: Analysis failed."

    except Exception as e:
        st.error(f"An unexpected error occurred while processing the uploaded file: {e}")
        st.exception(e)
        st.session_state.extracted_file_info = "Error: File processing error."

# --- Display Extracted File Info ---
if st.session_state.extracted_file_info:
    st.subheader("Extracted Information from Uploaded File")
    st.text_area("Extracted Details", st.session_state.extracted_file_info, height=400, key="displayed_extracted_file_info")

st.markdown("---")
st.markdown("Developed with Gemini & Streamlit.")
