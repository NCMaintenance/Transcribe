import streamlit as st
import base64
import requests # Make sure 'requests' is installed: pip install requests
import io # For handling byte streams for PDF/Image

# For PDF processing, user needs to install: pip install pdfplumber
import pdfplumber
# Pillow (PIL) might be needed by st.image or if doing image manipulations,
# often a Streamlit dependency. pip install Pillow

# --- Configuration ---
GEMINI_API_KEY = None
API_KEY_SOURCE = "Not loaded"

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE": # Basic check if it's not the placeholder
        API_KEY_SOURCE = "Streamlit Secrets"
    else: # It might be the placeholder if secrets.toml has it as placeholder
        GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE" # Ensure it's the placeholder
        API_KEY_SOURCE = "Placeholder (from Secrets or fallback)"
except KeyError:
    API_KEY_SOURCE = "Not found in Streamlit Secrets, using placeholder"
    GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE" # Fallback for local development
except AttributeError: 
    API_KEY_SOURCE = "Streamlit Secrets not available, using placeholder"
    GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE" # Fallback for local development
except Exception as e: # Catch any other unexpected errors during secrets access
    API_KEY_SOURCE = f"Error accessing Streamlit Secrets ({type(e).__name__}), using placeholder"
    GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

st.set_page_config(page_title="Dr. Scribe Enhanced", layout="wide")
st.title("Dr. Scribe - Enhanced Transcription & Note Analysis")

# --- Initialize Session State ---
if 'raw_transcript' not in st.session_state:
    st.session_state.raw_transcript = ""
if 'formatted_transcript' not in st.session_state:
    st.session_state.formatted_transcript = ""
if 'last_processed_audio_data' not in st.session_state:
    st.session_state.last_processed_audio_data = "" 
if 'extracted_file_info' not in st.session_state:
    st.session_state.extracted_file_info = ""


# --- API Key Check and Main App Intro ---
if API_KEY_SOURCE == "Streamlit Secrets":
    st.sidebar.success(f"Gemini API Key loaded successfully from {API_KEY_SOURCE}.")
elif API_KEY_SOURCE.startswith("Error accessing") or API_KEY_SOURCE.startswith("Streamlit Secrets not available"):
    st.sidebar.warning(f"{API_KEY_SOURCE}. Please check your Streamlit environment or secrets configuration.")
else: # Placeholder cases
    st.sidebar.warning(f"Gemini API Key: {API_KEY_SOURCE}. Update placeholder if needed.")


if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
    st.error("🔴 CRITICAL: Gemini API Key is not configured or is still the placeholder. The application will not function correctly.")
    st.markdown("""
    **To fix this:**
    - **If running on Streamlit Community Cloud:** Set `GEMINI_API_KEY` in your app's secrets in the Streamlit Cloud dashboard.
    - **If running locally:** 1. Create a file named `secrets.toml` in a folder named `.streamlit` in your app's root directory (i.e., `.streamlit/secrets.toml`).
        2. Add your API key to this file: `GEMINI_API_KEY = "your_actual_api_key_value"`
        3. Alternatively, you can replace `"YOUR_GEMINI_API_KEY_HERE"` directly in the script (less recommended for security).
    """)

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
    """
    Calls the Gemini API with the given payload.
    Returns the JSON response or None if an error occurs.
    """
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
    """
    Safely extracts text from Gemini API response.
    """
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        st.error(f"Failed to extract text from Gemini response: {e}")
        st.json(result) 
        return None

# --- JavaScript Recorder Widget ---
record_script = """
<script>
let mediaRecorder;
let audioChunks = [];
let stream; 

async function startRecording() {
    try {
        console.log("Attempting to start recording...");
        document.getElementById("record-status").innerText = "Initializing microphone...";
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log("Microphone stream obtained.");
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        console.log("MediaRecorder initialized with mimeType: audio/webm");
        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
                // console.log("Audio chunk received, size: " + event.data.size);
            } else {
                // console.log("Audio chunk received but size is 0.");
            }
        };

        mediaRecorder.onstop = () => {
            console.log("MediaRecorder stopped.");
            console.log("Number of audio chunks: " + audioChunks.length);
            if (audioChunks.length > 0) {
                console.log("Size of first audio chunk: " + (audioChunks[0] ? audioChunks[0].size : "N/A"));
            }

            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            console.log("Blob created. Size: " + blob.size + ", Type: " + blob.type);

            const reader = new FileReader();
            reader.onloadend = () => {
                console.log("FileReader onloadend triggered.");
                // console.log("Raw reader.result (first 100 chars): " + (reader.result ? reader.result.toString().substring(0,100) : "null/undefined"));
                
                let base64Audio = ""; 
                if (reader.result) {
                    const resultString = reader.result.toString();
                    const parts = resultString.split(',');
                    if (parts.length > 1) {
                        base64Audio = parts[1];
                        // console.log("Base64 audio data extracted (first 50 chars): " + base64Audio.substring(0,50));
                        // console.log("Base64 audio data length: " + base64Audio.length);
                    } else {
                        console.warn("FileReader result did not contain comma. Full result: ", resultString);
                    }
                } else {
                     console.warn("FileReader result is null or undefined.");
                }
                
                const input = document.getElementById('audio_data_input'); 
                if (input) {
                    input.value = base64Audio; 
                    console.log("Set input.value (length: " + base64Audio.length + "). Dispatching change event.");
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    console.error('Audio data input element not found');
                    document.getElementById("record-status").innerText = "Error: Could not send audio data to application.";
                }
            };
            reader.onerror = (error) => { 
                console.error("FileReader error:", error);
                document.getElementById("record-status").innerText = "Error: Could not read audio data.";
                const input = document.getElementById('audio_data_input');
                if (input) { 
                    input.value = ""; 
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
            };

            if (blob.size > 0) {
                console.log("Blob size > 0, calling reader.readAsDataURL(blob)");
                reader.readAsDataURL(blob);
            } else { 
                 console.warn("Recorded audio blob is empty. Not calling readAsDataURL.");
                 document.getElementById("record-status").innerText = "Warning: Recording was empty or too short.";
                 const input = document.getElementById('audio_data_input');
                 if (input) {
                    input.value = ""; 
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                 }
            }
            
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                console.log("Microphone stream tracks stopped.");
            }
        };

        mediaRecorder.start();
        console.log("MediaRecorder started.");
        document.getElementById("record-status").innerText = "Recording... Click 'Stop & Process' when done.";
        document.getElementById("start-record-btn").disabled = true;
        document.getElementById("stop-record-btn").disabled = false;
    } catch (err) {
        console.error("Error starting recording:", err);
        let errorMsg = "Error: Could not start recording.";
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
            errorMsg += " Please grant microphone permissions in your browser settings.";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
            errorMsg += " No microphone found. Please ensure a microphone is connected and enabled.";
        } else if (err.name === "NotReadableError") {
             errorMsg += " Microphone is already in use or a hardware error occurred.";
        }
        document.getElementById("record-status").innerText = errorMsg;
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
}

function stopRecording() {
    console.log("Stop recording button clicked.");
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop(); // This will trigger mediaRecorder.onstop
    } else {
        console.warn("Stop clicked but mediaRecorder not active or not initialized.");
        document.getElementById("record-status").innerText = "Idle. Click 'Start Recording'.";
        document.getElementById("start-record-btn").disabled = false;
        document.getElementById("stop-record-btn").disabled = true;
    }
    // Moved status update to onstop or error handlers for more accuracy
}

window.onload = () => {
    console.log("Window loaded. Initializing button states.");
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
    <input type="hidden" id="audio_data_input" />
</div>
"""
st.components.v1.html(record_script, height=220)

audio_data_base64_from_js = st.text_input("Audio Base64 (hidden, updated by JS)", key="audio_data_input_streamlit_key", label_visibility="collapsed")

# --- Audio Processing Logic ---
if audio_data_base64_from_js != st.session_state.last_processed_audio_data: 
    st.session_state.last_processed_audio_data = audio_data_base64_from_js

    proceed_with_api_call = False
    if not audio_data_base64_from_js: 
        st.warning("Received empty audio data. Please try recording again for a few seconds.")
        st.session_state.raw_transcript = "Error: Received empty audio data from recorder."
        st.session_state.formatted_transcript = ""
    elif not isinstance(audio_data_base64_from_js, str) or \
         audio_data_base64_from_js.lower() == "undefined" or \
         len(audio_data_base64_from_js) < 100:  # Increased threshold slightly for more robustness
        
        st.error(f"Audio data from recorder appears invalid or too short (e.g., 'undefined', or actual length {len(audio_data_base64_from_js)}). Please ensure the microphone is working and try recording again for at least a few seconds.")
        st.session_state.raw_transcript = "Error: Invalid or too short audio data received from recorder."
        st.session_state.formatted_transcript = ""
    else:
        proceed_with_api_call = True

    if proceed_with_api_call:
        if len(audio_data_base64_from_js) < 500: # Warn if a bit short
             st.warning(f"Recorded audio is quite short (data length: {len(audio_data_base64_from_js)} characters). Transcription quality may be affected. For best results, record for a longer duration.")

        st.info("New audio data received. Processing...")
        with st.spinner("Transcribing audio with Gemini..."):
            audio_payload = {
                "contents": [{
                    "parts": [
                        {"text": "Transcribe the following audio from a medical context accurately and clearly. Focus on medical terminology if present. Ensure the transcription is verbatim."},
                        {"inline_data": {
                            "mime_type": "audio/webm", # Ensure this matches JS recorder
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
                        st.session_state.formatted_transcript = "Error: Formatting failed (could not extract text from response)." 
                else:
                    st.error("Failed to get a formatting response from Gemini.")
                    st.session_state.formatted_transcript = "Error: No formatting response from Gemini." 
            else:
                st.error("Could not extract raw transcript from Gemini response.")
                st.session_state.raw_transcript = "Error: Transcription failed (could not extract text from response)." 
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
                        st.warning("No text could be extracted from this PDF. It might be an image-based PDF, encrypted, password-protected, or empty. For image-based PDFs, try uploading as an image file (e.g., PNG/JPG).")
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
            elif extracted_text_from_file or image_base64_for_gemini: # Only show error if an attempt was made
                st.error("Failed to get a response from Gemini for file analysis, or no text was extracted from the response.")
                st.session_state.extracted_file_info = "Error: Analysis failed."
            # If no content was available, no error message is needed here as warning was already shown.

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

# To run this app:
# 1. Save as a Python file (e.g., dr_scribe_app.py)
# 2. Install dependencies: pip install streamlit requests pdfplumber Pillow
# 3. Run from your terminal: streamlit run dr_scribe_app.py
# 4. Configure GEMINI_API_KEY as per instructions at the top of the app.

