import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")  # Suppress pandas SettingWithCopyWarning etc.

def format_time_duration(minutes):
    """Convert minutes to hours and minutes format if over 60 minutes"""
    if minutes == 0:
        return "0 minutes"
    elif minutes < 60:
        return f"{minutes} minutes"
    else:
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if remaining_minutes == 0:
            return f"{hours} hours"
        else:
            return f"{hours} hours {remaining_minutes} minutes"

# Set page configuration
st.set_page_config(
    page_title="Paediatric Waiting List",
    layout="wide",
    page_icon="https://www.ehealthireland.ie/media/k1app1wt/hse-logo-black-png.png"
)

# Constants for time calculations
WORK_DAY_MINUTES = 480  # 8-hour workday
WORK_DAYS_PER_WEEK = 5

# Session configurations
session_types = {
    "60 min": {
        "sessions_per_day": WORK_DAY_MINUTES // 60,
        "duration": 60,
        "daily_capacity": (WORK_DAY_MINUTES // 60) * 60
    },
    "50 min": {
        "sessions_per_day": WORK_DAY_MINUTES // 50,
        "duration": 50,
        "daily_capacity": (WORK_DAY_MINUTES // 50) * 50
    },
    "44 min": {
        "sessions_per_day": WORK_DAY_MINUTES // 44,
        "duration": 44,
        "daily_capacity": (WORK_DAY_MINUTES // 44) * 44
    }
}

def show_referral_charts(df):
    if "Referral_From" not in df.columns or "Category" not in df.columns:
        st.warning("The uploaded file must contain 'Referral_From' and 'Category' columns.")
        return

    st.subheader("📊 Referral Breakdown")
    
    # Calculate referral counts
    referral_counts = df.groupby(["Referral_From", "Category"]).size().reset_index(name="Count")
    
    # Calculate total referrals per referrer
    total_referrals = referral_counts.groupby("Referral_From")["Count"].sum().reset_index()
    
    # Layout for sorting & filtering controls
    col_sort, col_filter = st.columns([1, 1])

    with col_sort:
        category_filter = st.selectbox("Filter by category:", ["All", "P1", "P2", "P3", "P4"])

    with col_filter:
        min_referrals = st.slider("Show referrers with more than X referrals:", 
                          min_value=0, 
                          max_value=int(total_referrals["Count"].max()), 
                          value=3)
    
    # Apply category filter
    if category_filter != "All":
        referral_counts = referral_counts[referral_counts["Category"] == category_filter]

    # Apply referral count filter
    referrers_filtered = total_referrals[total_referrals["Count"] > min_referrals]["Referral_From"]
    filtered_referral_counts = referral_counts[referral_counts["Referral_From"].isin(referrers_filtered)].copy()

    # Sort referrers by total referrals descending
    sorted_referrers = total_referrals.sort_values(by="Count", ascending=False)["Referral_From"]
    
    filtered_referral_counts["Referral_From"] = pd.Categorical(filtered_referral_counts["Referral_From"], categories=sorted_referrers, ordered=True)
    filtered_referral_counts = filtered_referral_counts.sort_values("Referral_From")

    # Plot charts
    col1, col2 = st.columns(2)

    with col1:
        fig_bar = px.bar(filtered_referral_counts, x="Referral_From", y="Count", color="Category",
                         title="Referrals per Referrer by Category",
                         labels={"Count": "Number of Referrals"},
                         barmode="stack",
                         opacity=0.6,
                         color_discrete_map={"P1": "#FFFF00", "P2": "#00FF00", "P3": "#FFA500", "P4": "#FF0000"})
        st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        fig_sunburst = px.sunburst(filtered_referral_counts, path=["Referral_From", "Category"], values="Count",
                                   title="Referral Breakdown by Category and Referrer",
                                   color="Category",
                                   color_discrete_map={"P1": "#FFFF00", "P2": "#00FF00", "P3": "#FFA500", "P4": "#FF0000"})
        st.plotly_chart(fig_sunburst, use_container_width=True)

def calculate_extra_sessions(session_type, num_therapists, num_weeks):
    standard_duration = session_types["60 min"]["duration"]
    new_duration = session_types[session_type]["duration"]
    
    workday_standard_sessions = WORK_DAY_MINUTES // standard_duration
    workday_new_sessions = WORK_DAY_MINUTES // new_duration
    
    extra_sessions_per_day = workday_new_sessions - workday_standard_sessions
    extra_sessions_per_week = extra_sessions_per_day * WORK_DAYS_PER_WEEK * num_therapists
    total_extra_sessions = extra_sessions_per_week * num_weeks
    
    return total_extra_sessions, extra_sessions_per_day, extra_sessions_per_week

def simulate_backlog_reduction(session_key, strategy, num_therapists, sessions_per_therapist_per_week, avg_new_referrals_per_week, num_weeks, backlog_initial, avg_sessions_per_category, avg_weeks_between_sessions):
    """Simulate backlog reduction based on session configurations and strategies with follow-up sessions"""
    if num_therapists <= 0:
        raise ValueError("Number of therapists must be greater than 0")
    if sessions_per_therapist_per_week <= 0:
        raise ValueError("Sessions per therapist must be greater than 0")

    weeks = np.arange(1, num_weeks + 1)
    backlog_projection = {category: np.zeros(len(weeks)) for category in backlog_initial.keys()}
    patients_seen_per_week = {category: np.zeros(len(weeks)) for category in backlog_initial.keys()} 

    _, _, extra_sessions_per_week = calculate_extra_sessions(session_key, num_therapists, num_weeks)

    # Set initial backlog
    for category in backlog_initial.keys():
        backlog_projection[category][0] = backlog_initial[category]

    for i in range(1, len(weeks)):
        week_number = i + 1
        allocation = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}

        is_p3p4_week = (strategy == "1 in 4 weeks for P3/P4" and week_number % 4 == 0)

        if strategy == "1 in 4 weeks for P3/P4":
            if is_p3p4_week:
                allocation = {"P3": 0.5, "P4": 0.5, "P1": 0, "P2": 0}
            else:
                allocation = {"P1": 0.5, "P2": 0.5, "P3": 0, "P4": 0}
        elif strategy == "Even Split (50/50)":
            allocation = {"P1": 0.25, "P2": 0.25, "P3": 0.25, "P4": 0.25}
        else:  # Urgency-Weighted
            allocation = {"P1": 0.5, "P2": 0.3, "P3": 0, "P4": 0} ####### was .1 and .1 for p3 and 4

        for category in backlog_initial.keys():
            new_referrals = avg_new_referrals_per_week[category]

            base_weekly_sessions = sessions_per_therapist_per_week * num_therapists
            base_reduction = base_weekly_sessions * allocation[category]

            extra_reduction = 0
            if (category in ["P3", "P4"]) and (is_p3p4_week or strategy != "1 in 4 weeks for P3/P4"):
                extra_reduction = extra_sessions_per_week * allocation[category]

            total_reduction = base_reduction + extra_reduction

            avg_sessions = avg_sessions_per_category[category]
            avg_weeks_between = avg_weeks_between_sessions[category]

            follow_up_sessions = 0
            if week_number % avg_weeks_between == 0:
                follow_up_sessions = new_referrals * (avg_sessions - 1)

            if category in ['P1', 'P2']:
                if is_p3p4_week and strategy == "1 in 4 weeks for P3/P4":
                    new_backlog = backlog_projection[category][i-1] + new_referrals
                else:
                    new_backlog = backlog_projection[category][i-1] + new_referrals - total_reduction + follow_up_sessions
                    patients_seen_per_week[category][i] = total_reduction
            else:
                new_backlog = backlog_projection[category][i-1] + new_referrals - total_reduction + follow_up_sessions
                patients_seen_per_week[category][i] = total_reduction

            backlog_projection[category][i] = max(np.floor(new_backlog), 0)

    return weeks, backlog_projection, patients_seen_per_week

# Password protection using session state
if "password_verified" not in st.session_state:
    st.session_state.password_verified = False

if not st.session_state.password_verified:
    password = st.secrets["password"]
    st.image("https://www.ehealthireland.ie/media/k1app1wt/hse-logo-black-png.png", width=200)
    st.title("📃 Waiting List")
    user_password = st.text_input("Enter password to access the app:", type="password", key="password_input")
    submit_button = st.button("Submit")

    if submit_button:
        if user_password == password:
            st.session_state.password_verified = True
            st.rerun()
        else:
            st.warning("Incorrect password. Please try again.")
else:
    st.title("📃 Waiting List Optimisation")

    st.markdown("""
    This application helps optimise therapy waitlist management by:
    - Analysing current waitlist data
    - Projecting future waitlist trends
    - Simulating different scheduling strategies
    - Providing ML-based predictions
    """)

    uploaded_file = st.file_uploader("📂 Upload an Excel file with waiting list data", type=["xlsx"])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

            st.subheader("📊 Current Data Overview")
            st.write(df.head())

            # Sidebar configuration
            with st.sidebar:
                st.image("https://www.ehealthireland.ie/media/k1app1wt/hse-logo-black-png.png", width=200)
                st.title("📃 Waiting List")
                if st.button("Created by Dave Maher"):
                    st.sidebar.write("This application intellectual property belongs to Dave Maher.")
            
                st.header("⚙️ Configuration")
            
                num_therapists = st.number_input(
                    "👩‍⚕️ Number of Therapists",
                    min_value=1,
                    max_value=20,
                    value=1,
                    help="Enter the number of available therapists (1-20)"
                )
            
                sessions_per_therapist_per_week = st.number_input(
                    "🗓️ Sessions per Therapist per Week",
                    min_value=1,
                    max_value=40,
                    value=15,
                    help="Enter the number of sessions per therapist per week (1-40)"
                )
            
                num_weeks = st.selectbox(
                    "📅 Number of Weeks for Projection",
                    [12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52],
                    index=0
                )
            
                st.markdown("---")
                st.subheader("📊 Average Sessions and Weeks Between")
                avg_sessions_per_category = {
                    "P1": st.number_input("Average Sessions for P1", min_value=1, value=6),
                    "P2": st.number_input("Average Sessions for P2", min_value=1, value=4),
                    "P3": st.number_input("Average Sessions for P3", min_value=1, value=2),
                    "P4": st.number_input("Average Sessions for P4", min_value=1, value=1)
                }
                
                avg_weeks_between_sessions = {
                    "P1": st.number_input("Average Weeks Between Sessions for P1", min_value=1, value=4),
                    "P2": st.number_input("Average Weeks Between Sessions for P2", min_value=1, value=6),
                    "P3": st.number_input("Average Weeks Between Sessions for P3", min_value=1, value=8),
                    "P4": st.number_input("Average Weeks Between Sessions for P4", min_value=1, value=12)
                }

            st.markdown("---")
            # Initial backlog counts
            st.subheader("🔄️ Initial Backlog Counts")
            backlog_initial = {
                category: df[df["Category"] == category]["Wait_Time"].count()
                for category in ["P1", "P2", "P3", "P4"]
            }
            total_patients = sum(backlog_initial.values())
            backlog_percentage = {
                category: round((count / total_patients) * 100, 0)
                for category, count in backlog_initial.items()
            }

            # Display backlog metrics
            columns = st.columns(5)
            colors = {"P1": "#FFFF00", "P2": "#00FF00", "P3": "#FFA500", "P4": "#FF0000", "Total": "#0000FF"}
            categories = ["P1", "P2", "P3", "P4", "Total"]

            for i, category in enumerate(categories):
                with columns[i]:
                    if category == "Total":
                        st.metric(f"{category} Patients", total_patients)
                        st.markdown("""
                            <div style="background-color: #0000FF; width: 100%; height: 20px; opacity: 0.6;"></div>
                        """, unsafe_allow_html=True)
                    else:
                        st.metric(f"{category} Patients", backlog_initial[category])
                        progress_color = colors[category]
                        st.markdown(f"""
                            <div style="background-color: {progress_color}; width: {backlog_percentage[category]}%; height: 20px; opacity: 0.6;"></div>
                        """, unsafe_allow_html=True)
                        st.write(f"{backlog_percentage[category]:.0f}% of total")

            # Calculate weekly referrals with more detailed calculation
            df['Week'] = df['Date'].dt.isocalendar().week
            new_referrals_per_week = df.groupby(['Week', 'Category']).size().unstack(fill_value=0)

            # Calculate average weekly referrals with minimum values to ensure growth
            avg_new_referrals_per_week = pd.Series({
                'P1': max(new_referrals_per_week['P1'].mean(), 1),  # Ensure at least 1 new P1 per week
                'P2': max(new_referrals_per_week['P2'].mean(), 2),  # Ensure at least 2 new P2 per week
                'P3': new_referrals_per_week['P3'].mean(),
                'P4': new_referrals_per_week['P4'].mean()
            })

            st.markdown("---")

            # Session configuration and strategy selection
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("⚙️ Session Configuration")
                selected_session = st.radio(
                    "🕒 Session length (Weeks P3/P4):",
                    ["60 min", "50 min", "44 min"]
                )
            with col2:
                st.subheader("📅 Scheduling Strategy")
                selected_strategy = st.selectbox(
                    "📌 Select strategy:",
                    [
                        "1 in 4 weeks for P3/P4",
                        "Even Split (50/50)",
                        "Urgency-Weighted Scheduling"
                    ],
                    index=2
                )

            # Run simulation and display results
            try:
                weeks, backlog_projection, patients_seen_per_week = simulate_backlog_reduction(
                    selected_session,
                    selected_strategy,
                    num_therapists,
                    sessions_per_therapist_per_week,
                    avg_new_referrals_per_week,
                    num_weeks,
                    backlog_initial,
                    avg_sessions_per_category,  # Pass the average sessions per category
                    avg_weeks_between_sessions  # Pass the average weeks between sessions
                )
            
                # Display the chart
                st.subheader("📉 Simulation Results")
                fig = go.Figure()
                for category, projection in backlog_projection.items():
                    fig.add_trace(go.Scatter(
                        x=weeks,
                        y=projection,
                        mode='lines+markers',
                        name=f'{category} Backlog',
                        line=dict(color=colors[category]),
                        hovertemplate="Week: %{x}<br>" + category + ": %{y} patients"
                    ))
                fig.update_layout(
                    title=f"📉 Backlog Reduction Over {num_weeks} Weeks",
                    xaxis_title="Weeks",
                    yaxis_title="Number of Patients"
                )
                st.plotly_chart(fig, use_container_width=True)
            
                # Display efficiency metrics
                st.markdown("---")
                st.subheader("🎯 Efficiency Metrics")
                col1, col2 = st.columns(2)
            
                with col1:
                    total_extra_sessions, extra_sessions_per_day, extra_sessions_per_week = calculate_extra_sessions(
                        selected_session,
                        num_therapists,
                        num_weeks
                    )
            
                    st.metric(
                        "Extra Sessions for P3/P4",
                        f"{extra_sessions_per_day} sessions per day per therapist"
                    )
                    st.metric(
                        "Extra Weekly P3/P4 Capacity",
                        f"{extra_sessions_per_week} sessions per week (all therapists)"
                    )
            
                with col2:
                    p3p4_weeks = num_weeks // 4 if selected_strategy == "1 in 4 weeks for P3/P4" else num_weeks
                    total_minutes_saved = (
                        session_types["60 min"]["duration"] - 
                        session_types[selected_session]["duration"]
                    ) * extra_sessions_per_week * p3p4_weeks
            
                    st.metric(
                        "Total Extra P3/P4 Sessions",
                        f"{total_extra_sessions} sessions in {p3p4_weeks} P3/P4 weeks"
                    )
                    st.metric(
                        "Total Time Saved in P3/P4 Weeks",
                        format_time_duration(total_minutes_saved)
                    )
            
                st.markdown("---")
                show_referral_charts(df)
            
            except Exception as e:
                st.error(f"Error in simulation: {str(e)}")
        except Exception as e:
            st.error(f"An error occurred while processing the file: {str(e)}")
    else:
        st.info("👆 Please upload an Excel file to begin the analysis")

    # Add footer
    st.markdown("---")
    st.markdown("This implementation has been tested using test data. Adjustments may be required to ensure optimal performance with real-world waiting list data.")
    st.markdown("Created by Dave Maher")
# import streamlit as st
# import google.generativeai as genai
# import json
# import os
# from datetime import datetime
# from docx import Document
# import io
# import tempfile
# import re

# # --- Configure Gemini API ---
# genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
# model = genai.GenerativeModel(model_name='gemini-2.0-flash-exp')

# st.set_page_config(page_title="Dr. Scribe", layout="wide")
# st.title("🩺 Dr. Scribe")
# st.markdown("### 📤 Upload or Record Doctor–Patient Audio")

# # --- Input Method Selection ---
# mode = st.radio("Choose input method:", ["Upload audio file", "Record using microphone"])

# audio_bytes = None
# audio_format = "audio/wav"

# if mode == "Upload audio file":
#     uploaded_audio = st.file_uploader("Upload an audio file (WAV, MP3, M4A)", type=["wav", "mp3", "m4a"])
#     if uploaded_audio:
#         st.audio(uploaded_audio, format=audio_format)
#         audio_bytes = uploaded_audio  # File-like object

# elif mode == "Record using microphone":
#     recorded_audio = st.audio_input("🎙️ Click the microphone to record, then click again to stop and process.")
#     if recorded_audio:
#         st.audio(recorded_audio, format=audio_format)
#         audio_bytes = recorded_audio  # Already in bytes

# # --- Transcription and Analysis ---
# if audio_bytes and st.button("🧠 Transcribe & Analyse"):
#     with st.spinner("Processing with Gemini..."):

#         # Convert to bytes if it's a file-like object
#         if hasattr(audio_bytes, "read"):
#             audio_bytes = audio_bytes.read()

#         # Save to temporary file
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
#             tmp_file.write(audio_bytes)
#             tmp_file_path = tmp_file.name

#         try:
#             audio_file = genai.upload_file(path=tmp_file_path)

#             prompt = (
#                 "You are a medical transcriptionist. Transcribe the following doctor–patient consultation. "
#                 "Label speakers as 'Doctor:' or 'Patient:' where possible."
#             )
#             result = model.generate_content([prompt, audio_file], request_options={"timeout": 600})
#             transcript = result.text
#             genai.delete_file(audio_file.name)

#             st.session_state["transcript"] = transcript
#             st.success("Transcript generated successfully.")
#         finally:
#             os.remove(tmp_file_path)

# # --- Display Transcript ---
# if "transcript" in st.session_state:
#     st.markdown("## 📄 Transcript")
#     st.text_area("Transcript", st.session_state["transcript"], height=300)

#     if st.button("📊 Summarise Transcript"):
#         with st.spinner("Generating structured and narrative summaries..."):

#             # --- Structured Summary ---
#             prompt_structured = f"""
# You are a medical scribe. Extract key details from this doctor–patient transcript and return JSON with:
# - patientName
# - dateOfVisit
# - chiefComplaint
# - historyPresentIllness
# - pastMedicalHistory
# - medications
# - allergies
# - reviewOfSystems
# - physicalExam
# - assessment
# - plan
# - followUp

# If not mentioned, use "Not mentioned".
# Transcript:
# {st.session_state['transcript']}
#             """
#             response1 = model.generate_content(prompt_structured)

#             # Parse JSON safely
#             json_match = re.search(r"\{.*\}", response1.text, re.DOTALL)
#             if json_match:
#                 try:
#                     structured = json.loads(json_match.group())
#                 except json.JSONDecodeError as e:
#                     st.error("❌ JSON found but failed to parse. Check formatting.")
#                     st.code(json_match.group(), language="json")
#                     raise e
#             else:
#                 st.error("❌ No valid JSON object found in Gemini's response.")
#                 st.code(response1.text)
#                 raise ValueError("No valid JSON found.")

#             # --- Narrative Summary ---
#             prompt_narrative = f"""
# Summarise the transcript into a coherent, professional doctor’s narrative summary using appropriate medical language.
# Transcript:
# {st.session_state['transcript']}
#             """
#             response2 = model.generate_content(prompt_narrative)
#             narrative = response2.text

#             st.session_state["structured"] = structured
#             st.session_state["narrative"] = narrative
#             st.success("Summaries generated.")

# # --- DOCX Export Function ---
# def create_docx(content, kind="structured"):
#     doc = Document()
#     if kind == "structured":
#         doc.add_heading("Structured Medical Summary", level=1)
#         for key, val in content.items():
#             doc.add_heading(key.replace('_', ' ').title(), level=2)
#             doc.add_paragraph(val)
#     else:
#         doc.add_heading("Doctor’s Narrative Summary", level=1)
#         doc.add_paragraph(content)
#     output = io.BytesIO()
#     doc.save(output)
#     output.seek(0)
#     return output

# # --- Display Summaries and Downloads ---
# if "structured" in st.session_state and "narrative" in st.session_state:
#     st.markdown("## 📑 Structured Summary")
#     for k, v in st.session_state["structured"].items():
#         st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")

#     st.download_button("📥 Download Structured Summary (DOCX)",
#         data=create_docx(st.session_state["structured"], "structured"),
#         file_name="structured_summary.docx",
#         mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

#     st.markdown("---")
#     st.markdown("## 🧑‍⚕️ Doctor’s Narrative Summary")
#     st.write(st.session_state["narrative"])

#     st.download_button("📥 Download Narrative Summary (DOCX)",
#         data=create_docx(st.session_state["narrative"], "narrative"),
#         file_name="narrative_summary.docx",
#         mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")




# # import streamlit as st
# # import google.generativeai as genai
# # import json
# # import os
# # from datetime import datetime
# # from docx import Document
# # import io
# # import tempfile

# # # --- Set up Gemini API ---
# # genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
# # model = genai.GenerativeModel("gemini-1.5-pro-latest")

# # st.set_page_config(page_title="Dr. Scribe", layout="wide")
# # st.title("🩺 Dr. Scribe")
# # st.markdown("### 📤 Upload Doctor-Patient Audio")

# # # --- Upload Audio File ---
# # uploaded_audio = st.file_uploader("Upload an audio file (WAV, MP3, M4A)", type=["wav", "mp3", "m4a"])

# # if uploaded_audio:
# #     st.audio(uploaded_audio, format="audio/wav")

# #     if st.button("🧠 Transcribe & analyse"):
# #         with st.spinner("Processing with Gemini..."):

# #             # Save audio to temp file
# #             with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
# #                 tmp_file.write(uploaded_audio.read())
# #                 tmp_file_path = tmp_file.name

# #             # Upload to Gemini
# #             audio_file = genai.upload_file(path=tmp_file_path)

# #             # --- Transcription Prompt ---
# #             prompt = ("You are a medical transcriptionist. Transcribe the following doctor-patient consultation. "
# #                       "Label speakers as 'Doctor:' or 'Patient:' when possible.")
# #             result = model.generate_content([prompt, audio_file], request_options={"timeout": 600})
# #             transcript = result.text
# #             genai.delete_file(audio_file.name)
# #             os.remove(tmp_file_path)

# #             st.session_state["transcript"] = transcript
# #             st.success("Transcript generated!")

# # # --- Show Transcript ---
# # if "transcript" in st.session_state:
# #     st.markdown("## 📄 Transcript")
# #     st.text_area("Transcript", st.session_state["transcript"], height=300)

# #     if st.button("📊 Summarize Transcript"):
# #         with st.spinner("Generating structured and narrative summaries..."):

# #             # --- Structured Summary ---
# #             prompt_structured = f"""
# # You are a medical scribe. Extract key details from this doctor-patient transcript and return JSON with:
# # - patientName
# # - dateOfVisit
# # - chiefComplaint
# # - historyPresentIllness
# # - pastMedicalHistory
# # - medications
# # - allergies
# # - reviewOfSystems
# # - physicalExam
# # - assessment
# # - plan
# # - followUp

# # If not mentioned, use "Not mentioned".
# # Transcript:
# # {st.session_state['transcript']}
# #             """
# #             response1 = model.generate_content(prompt_structured)
# #             structured = json.loads(response1.text)

# #             # --- Narrative Summary ---
# #             prompt_narrative = f"""
# # Summarize the transcript into a coherent, professional doctor’s narrative summary using appropriate medical language.
# # Transcript:
# # {st.session_state['transcript']}
# #             """
# #             response2 = model.generate_content(prompt_narrative)
# #             narrative = response2.text

# #             st.session_state["structured"] = structured
# #             st.session_state["narrative"] = narrative
# #             st.success("Summaries ready.")

# # # --- Display Summaries ---
# # def create_docx(content, kind="structured"):
# #     doc = Document()
# #     if kind == "structured":
# #         doc.add_heading("Structured Medical Summary", level=1)
# #         for key, val in content.items():
# #             doc.add_heading(key.replace('_', ' ').title(), level=2)
# #             doc.add_paragraph(val)
# #     else:
# #         doc.add_heading("Doctor's Narrative Summary", level=1)
# #         doc.add_paragraph(content)
# #     output = io.BytesIO()
# #     doc.save(output)
# #     output.seek(0)
# #     return output

# # if "structured" in st.session_state and "narrative" in st.session_state:
# #     st.markdown("## 📑 Structured Summary")
# #     for k, v in st.session_state["structured"].items():
# #         st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")

# #     st.download_button("📥 Download Structured Summary (DOCX)",
# #         data=create_docx(st.session_state["structured"], "structured"),
# #         file_name="structured_summary.docx",
# #         mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# #     st.markdown("---")
# #     st.markdown("## 🧑‍⚕️ Doctor's Narrative Summary")
# #     st.write(st.session_state["narrative"])

# #     st.download_button("📥 Download Narrative Summary (DOCX)",
# #         data=create_docx(st.session_state["narrative"], "narrative"),
# #         file_name="narrative_summary.docx",
# #         mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
