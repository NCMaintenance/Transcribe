import streamlit as st
from transformers import pipeline

st.set_page_config(page_title="Dr. Script", page_icon="🩺")

st.title("🩺 Dr. Script")
st.subheader("Real-time Doctor-Patient Transcript Summarizer")

st.markdown("""
Enter or paste a transcript of a doctor-patient conversation below.  
Dr. Script will generate summarized doctor notes—just like Heidi AI.
""")

# Initialize summarization pipeline (loads on first run)
@st.cache_resource
def load_summarizer():
    return pipeline("summarization", model="facebook/bart-large-cnn")

summarizer = load_summarizer()

# Simulate real-time input
transcript = st.text_area(
    "Paste the doctor-patient transcript here:",
    height=250,
    placeholder="e.g.\nDoctor: How are you feeling today?\nPatient: I have a headache and some nausea...",
)

if st.button("Generate Doctor Notes") and transcript.strip():
    with st.spinner("Summarizing..."):
        # BART has a max token limit, so chunk if needed
        max_chunk = 1024
        transcript_chunks = [transcript[i:i+max_chunk] for i in range(0, len(transcript), max_chunk)]
        summaries = []
        for chunk in transcript_chunks:
            summary = summarizer(chunk, min_length=50, max_length=180, do_sample=False)[0]['summary_text']
            summaries.append(summary)
        final_summary = "\n".join(summaries)
    st.success("Doctor Notes Generated:")
    st.text_area("Doctor Notes:", final_summary, height=200)

st.markdown("---")
st.caption("Powered by Streamlit & HuggingFace Transformers")
