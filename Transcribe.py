import streamlit as st
import base64
import requests
from datetime import datetime
from PIL import Image
import io

st.set_page_config(page_title="Doctor-Patient Note Processor", layout="centered")

st.title("Doctor-Patient Note Processor")
st.write("Record audio conversations or upload scanned letters for Gemini to process.")

# --- Gemini API key ---
api_key = st.text_input("Gemini API Key", type="password")
st.caption("Your API key is used client-side. For production, manage keys securely on a backend.")

# --- Helper: Gemini API Call ---
def call_gemini(prompt, base64_data, mime_type, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    parts = [{"text": prompt}]
    if base64_data and mime_type:
        parts.append({"inlineData": {"mimeType": mime_type, "data": base64_data}})
    data = {"contents": [{"role": "user", "parts": parts}]}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        result = response.json()
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except Exception:
            return "Unexpected response structure."
    else:
        return f"Error: {response.status_code} - {response.text}"

# --- Audio Upload Section ---
st.subheader("Audio Conversation Processing")
audio_file = st.file_uploader("Upload Recorded Audio", type=["webm", "mp3", "wav"])
if audio_file:
    st.audio(audio_file)
    if st.button("Transcribe & Structure Audio"):
        with st.spinner("Processing audio..."):
            audio_bytes = audio_file.read()
            base64_audio = base64.b64encode(audio_bytes).decode()
            mime_type = audio_file.type

            audio_prompt = """
You are an expert medical transcriber and note-taker.
The following is base64 encoded audio data from a doctor-patient conversation.
1. Transcribe the conversation.
2. Structure the entire conversation into a clear medical note with the following sections:
- Patient's Full Name:
- Date of Consultation:
- Chief Complaint / Reason for Visit:
- History of Present Illness:
- Doctor's Observations & Examination Findings:
- Assessment / Diagnosis:
- Treatment Plan / Recommendations:
- Follow-up Instructions:
- Any other important notes:

Output format:

--- TRANSCRIPTION ---
[Conversation transcript]

--- STRUCTURED MEDICAL NOTE ---
[Structured content]
"""
            if api_key:
                result = call_gemini(audio_prompt, base64_audio, mime_type, api_key)
                st.text_area("Result", result, height=300)
            else:
                st.error("Please provide your Gemini API Key.")

# --- OCR Image Upload Section ---
st.subheader("Scanned Letter Processing (OCR)")
image_file = st.file_uploader("Upload Scanned Letter Image", type=["png", "jpg", "jpeg"])
if image_file:
    image = Image.open(image_file)
    st.image(image, caption="Uploaded Image", use_column_width=True)

    if st.button("Extract & Structure Letter"):
        with st.spinner("Processing image..."):
            image_bytes = image_file.read()
            base64_image = base64.b64encode(image_bytes).decode()
            mime_type = image_file.type

            image_prompt = f"""
You are an expert Optical Character Recognition (OCR) system and document analyzer.
The following is a base64 encoded image of a scanned letter (MIME type: {mime_type}).
1. Extract all text from the image.
2. Structure the information from the letter. Identify and list the following if present:
- Sender's Name:
- Sender's Address:
- Recipient's Name:
- Recipient's Address:
- Date of Letter:
- Subject / Summary:
- Main Body:
- Signature / Closing:

Output format:
--- EXTRACTED TEXT ---
[Full extracted content]

--- STRUCTURED LETTER CONTENT ---
[Structured content]
"""
            if api_key:
                result = call_gemini(image_prompt, base64_image, mime_type, api_key)
                st.text_area("Result", result, height=300)
            else:
                st.error("Please provide your Gemini API Key.")
