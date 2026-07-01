import streamlit as st
import os
import json
from datetime import datetime, date
from utils.storage import (
    load_data, save_data, update_profile, update_syllabus, toggle_topic_status,
    register_user, authenticate_user, get_user_plans, create_study_plan, delete_study_plan, save_study_plan
)
from utils.pdf_parser import extract_text_from_pdf, parse_syllabus_topics, merge_syllabi
from agents.planner_agent import StudyPlannerAgent
from agents.quiz_agent import QuizAgent
from agents.recommendation_agent import RecommendationAgent
from agents.notes_agent import NotesAgent
from agents.assistant_agent import AssistantAgent
from utils.gemini_helper import call_gemini, is_api_available, HAS_REAL_KEY
import plotly.express as px

st.set_page_config(
    page_title="AI Student Study Planner Agent",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .dashboard-card { background-color: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; border-left: 5px solid #4F46E5; }
    .metric-card { background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: white; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2); }
    .metric-value { font-size: 2.2rem; font-weight: 700; margin: 10px 0; }
    .metric-label { font-size: 0.9rem; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; }
    h1, h2, h3 { color: #1e1b4b; font-family: 'Outfit', sans-serif; }
    .rec-high { border-left: 5px solid #ef4444; background-color: #fef2f2; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .rec-medium { border-left: 5px solid #f59e0b; background-color: #fffbeb; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .rec-low { border-left: 5px solid #10b981; background-color: #ecfdf5; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .reasoning-box { background-color: #f3f4f6; border-left: 5px solid #6b7280; padding: 15px; border-radius: 8px; font-style: italic; margin-bottom: 20px; }
    
    .plan-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 15px; border: 1px solid #e5e7eb; }
</style>
""", unsafe_allow_html=True)

# ----------------- AUTHENTICATION ----------------- #
if not st.session_state.get("authenticated", False):
    st.markdown("<div style='text-align: center; padding: 50px 0;'><h1>🎓 Welcome to StudyAgent</h1><p>Your AI Learning Partner</p></div>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login to your account")
        with st.form("login_form"):
            l_username = st.text_input("Username")
            l_password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                success, fullname = authenticate_user(l_username, l_password)
                if success:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = l_username
                    st.session_state["fullname"] = fullname
                    st.session_state["active_plan_id"] = None
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
                    
    with tab2:
        st.subheader("Create a new account")
        with st.form("register_form"):
            r_fullname = st.text_input("Full Name")
            r_username = st.text_input("Username")
            r_email = st.text_input("Email Address")
            r_password = st.text_input("Password", type="password")
            r_confirm = st.text_input("Confirm Password", type="password")
            if st.form_submit_button("Register"):
                if r_password != r_confirm:
                    st.error("Passwords do not match.")
                elif not all([r_fullname, r_username, r_email, r_password]):
                    st.error("Please fill in all fields.")
                else:
                    success, msg = register_user(r_fullname, r_username, r_email, r_password)
                    if success:
                        st.success("Registration successful! You can now log in.")
                    else:
                        st.error(msg)
    st.stop()

# ----------------- SIDEBAR ----------------- #
st.sidebar.markdown("<div style='text-align: center; padding-bottom: 20px;'><h1>🎓 StudyAgent</h1></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"**👤 {st.session_state.get('fullname')}**")

if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Determine available navigation
active_plan_id = st.session_state.get("active_plan_id")
if not active_plan_id:
    nav_options = ["Home (Dashboard)"]
else:
    nav_options = [
        "Home (Dashboard)",
        "Student Profile", 
        "Upload Syllabus PDF", 
        "Manual Topic Study",
        "Study Planner", 
        "Quiz Generator", 
        "AI Notes Generator",
        "AI Study Assistant",
        "Progress Tracker", 
        "Recommendations",
        "🔌 MCP Developer Panel"
    ]
    st.sidebar.markdown("---")
    if st.sidebar.button("Close Active Plan"):
        st.session_state["active_plan_id"] = None
        st.rerun()

nav_index = 0
if "nav_override" in st.session_state:
    if st.session_state["nav_override"] in nav_options:
        nav_index = nav_options.index(st.session_state["nav_override"])
    del st.session_state["nav_override"]

page = st.sidebar.radio("Navigation Menu", nav_options, index=nav_index)

# Helper functions
def get_countdown(exam_date_str):
    """
    Calculates the number of days remaining until the exam date.
    Returns the integer number of days, or None if invalid.
    """
    if not exam_date_str: return None
    try:
        return (datetime.strptime(exam_date_str, "%Y-%m-%d").date() - date.today()).days
    except:
        return None

# Load state if plan is active
state = load_data(st.session_state["username"], active_plan_id) if active_plan_id else {}
profile = state.get("profile", {})
syllabus = state.get("syllabus", {"reasoning": "", "units": []})
completed_topics = state.get("completed_topics", [])
study_plan = state.get("study_plan", [])

def get_flat_topics():
    """
    Flattens the structured syllabus into a single list of topic strings 
    for easy counting and rendering.
    """
    return [f"{u.get('unit_name', 'Unit')} - {t}" for u in syllabus.get("units", []) for t in u.get("topics", [])]

if active_plan_id:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Active Plan Context")
    st.sidebar.text(f"📚 Subject: {profile.get('subject', 'Not set')}")
    cd = get_countdown(profile.get("exam_date"))
    if cd is not None:
        if cd > 0: st.sidebar.info(f"⏳ {cd} Days to Exam")
        elif cd == 0: st.sidebar.warning("⏳ Exam is TODAY!")
        else: st.sidebar.error("⏳ Exam date has passed.")

# ----------------- MAIN APP LOGIC ----------------- #

if page == "Home (Dashboard)":
    st.markdown(f"<h1>Welcome back, {st.session_state.get('fullname')} 👋</h1>", unsafe_allow_html=True)
    
    if not active_plan_id:
        st.markdown("### My Study Plans")
        plans = get_user_plans(st.session_state["username"])
        if plans:
            for p in plans:
                with st.container():
                    st.markdown(f"""
                    <div class="plan-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h3 style="margin: 0; color: #4F46E5;">{p['name']}</h3>
                                <p style="margin: 5px 0 0 0; color: #6b7280;">Subject: {p['subject']} | Mode: {p['mode']} | Modified: {p['last_modified'][:10]}</p>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    col1, col2, _ = st.columns([1, 1, 8])
                    if col1.button("📂 Open Plan", key=f"open_{p['plan_id']}"):
                        st.session_state["active_plan_id"] = p['plan_id']
                        st.session_state.pop("active_notes", None)
                        st.rerun()
                    if col2.button("🗑️ Delete", key=f"del_{p['plan_id']}"):
                        delete_study_plan(st.session_state["username"], p['plan_id'])
                        st.rerun()
        else:
            st.info("You don't have any study plans yet. Create one below!")
            
        st.markdown("---")
        st.markdown("### ➕ Create New Study Plan")
        with st.form("new_plan_form"):
            np_name = st.text_input("Study Plan Name (e.g. Finals 2026)")
            np_subject = st.text_input("Subject")
            if st.form_submit_button("Create Plan"):
                if np_name and np_subject:
                    mode_val = "Not Set"
                    new_id = create_study_plan(st.session_state["username"], np_name, np_subject, mode_val)
                    st.session_state["active_plan_id"] = new_id
                    st.success("Plan created successfully!")
                    st.rerun()
                else:
                    st.error("Please provide both Plan Name and Subject.")
    
    else: # Active Plan Dashboard
        # Header showing Plan Name and Actions
        current_plan_name = "Study Plan"
        current_plan_mode = "Not Set"
        current_plan_mod = ""
        total_plans = 0
        plans = get_user_plans(st.session_state["username"])
        if plans:
            total_plans = len(plans)
            for p in plans:
                if p["plan_id"] == active_plan_id:
                    current_plan_name = p["name"]
                    current_plan_mode = p["mode"]
                    current_plan_mod = p["last_modified"][:10]
                    break
        
        st.markdown(f"<h2>{current_plan_name} Dashboard</h2>", unsafe_allow_html=True)
        
        # Quick Actions Row
        col_qa1, col_qa2, col_qa3, col_qa4 = st.columns(4)
        if col_qa1.button("📚 Manual Topic Study"):
            st.session_state["nav_override"] = "Manual Topic Study"
            st.rerun()
        if col_qa2.button("📝 Generate Quiz"):
            st.session_state["nav_override"] = "Quiz Generator"
            st.rerun()
        if col_qa3.button("📓 Generate Notes"):
            st.session_state["nav_override"] = "AI Notes Generator"
            st.rerun()
        if col_qa4.button("💬 Open AI Assistant"):
            st.session_state["nav_override"] = "AI Study Assistant"
            st.rerun()
        
        st.markdown("---")
        
        countdown = get_countdown(profile.get("exam_date"))
        flat_topics = get_flat_topics()
        total_t = len(flat_topics)
        completed_t = len(completed_topics)
        remaining_t = total_t - completed_t
        progress_pct = int((completed_t / total_t) * 100) if total_t > 0 else 0
        total_units = len(syllabus.get("units", []))
        
        # Summary Metric Cards Row 1
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Exam Countdown", f"{countdown} days" if countdown is not None else "--")
        col2.metric("Total Units", total_units)
        col3.metric("Total Topics", total_t)
        col4.metric("Total Study Plans", total_plans)
        
        # Summary Metric Cards Row 2
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Completed Topics", completed_t)
        col6.metric("Remaining Topics", remaining_t)
        col7.metric("Overall Progress", f"{progress_pct}%")
        col8.metric("Daily Goal", f"{profile.get('study_hours_per_day', 0)} hrs")
            
        st.markdown("---")
        
        # Charts Row
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.markdown("<h3>Progress Overview</h3>", unsafe_allow_html=True)
            if total_t > 0:
                fig_pie = px.pie(
                    names=["Completed", "Remaining"],
                    values=[completed_t, remaining_t],
                    hole=0.4,
                    color_discrete_sequence=["#10B981", "#E5E7EB"]
                )
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Add topics to see your progress chart.")
                
        with chart_col2:
            st.markdown("<h3>Unit-wise Completion</h3>", unsafe_allow_html=True)
            if total_units > 0:
                unit_names = []
                unit_progress = []
                for u in syllabus.get("units", []):
                    u_name = u.get("unit_name", "Unit")
                    u_topics = u.get("topics", [])
                    u_total = len(u_topics)
                    if u_total == 0: continue
                    
                    # Check how many topics in this unit are completed
                    # Topic representation in completed_topics: "Unit Name - Topic Name"
                    u_completed = 0
                    for t in u_topics:
                        if f"{u_name} - {t}" in completed_topics:
                            u_completed += 1
                            
                    pct = (u_completed / u_total) * 100
                    unit_names.append(u_name[:15] + "..." if len(u_name)>15 else u_name)
                    unit_progress.append(pct)
                
                if unit_names:
                    fig_bar = px.bar(
                        x=unit_names, 
                        y=unit_progress, 
                        labels={"x": "Unit", "y": "Completion %"},
                        color_discrete_sequence=["#3B82F6"]
                    )
                    fig_bar.update_layout(yaxis_range=[0,100], margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Setup syllabus units to see unit-wise progress.")
        
        st.markdown("---")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("<div class='dashboard-card'><h3>📅 Upcoming Study Tasks</h3>", unsafe_allow_html=True)
            if study_plan:
                for day_item in study_plan[:3]:
                    st.write(f"**Day {day_item['day']}:** {day_item['task']} *({day_item['hours']} hours)*")
                
                st.markdown("#### 📥 Export Study Plan")
                from utils.export_helper import export_plan_csv, export_plan_pdf
                dl_c1, dl_c2 = st.columns(2)
                dl_c1.download_button("Download CSV", data=export_plan_csv(study_plan), file_name="study_plan.csv", mime="text/csv")
                dl_c2.download_button("Download PDF", data=export_plan_pdf(study_plan), file_name="study_plan.pdf", mime="application/pdf")
            else:
                st.info("No study plan generated yet. Go to the **Study Planner** page.")
            st.markdown("</div>", unsafe_allow_html=True)
            
        with c2:
            st.markdown("<div class='dashboard-card'><h3>✨ Plan Info & Agent Status</h3>", unsafe_allow_html=True)
            if is_api_available(): st.success("🤖 Gemini API: Connected")
            else: st.info("🤖 Mode: Mock Fallback")
            st.write(f"**Subject:** {profile.get('subject')}")
            st.write(f"**Exam Date:** {profile.get('exam_date')}")
            st.write(f"**Material Type:** {current_plan_mode}")
            st.write(f"**Last Modified:** {current_plan_mod}")
            
            # Simple projected completion calculation
            if completed_t < total_t and profile.get("study_hours_per_day", 0) > 0:
                hours_per_topic = 1.5 # Arbitrary estimate
                hours_needed = remaining_t * hours_per_topic
                days_needed = hours_needed / profile.get("study_hours_per_day")
                try:
                    est_date = (date.today() + timedelta(days=int(days_needed))).strftime('%Y-%m-%d')
                    st.write(f"**Est. Completion:** {est_date}")
                except: pass
            
            st.markdown("</div>", unsafe_allow_html=True)

elif page == "Student Profile":
    st.markdown("<h1>👤 Student Profile Setup</h1>", unsafe_allow_html=True)
    
    fullname = st.session_state.get("fullname", "Student")
    username = st.session_state.get("username", "")
    
    st.markdown(f"**Welcome, {fullname}**")
    st.markdown(f"*Username: {username}*")
    st.markdown("---")
    
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            course = st.text_input("Course/Branch", value=profile.get("course", ""))
            semester = st.text_input("Semester (Optional)", value=profile.get("semester", ""))
            subject = st.text_input("Subject Name", value=profile.get("subject", ""))
        with col2:
            ed_val = datetime.strptime(profile["exam_date"], "%Y-%m-%d").date() if profile.get("exam_date") else date.today()
            exam_date = st.date_input("Exam Date", value=ed_val)
            study_hours = st.slider("Target Study Hours Per Day", 1, 12, int(profile.get("study_hours_per_day", 4)))
            
        if st.form_submit_button("Save Profile Settings"):
            update_profile(fullname, course, subject, exam_date, study_hours, len(syllabus.get("units", [])), semester)
            st.success("✅ Profile successfully updated!")
            st.rerun()

elif page == "Upload Syllabus PDF":
    st.markdown("<h1>📄 Upload Study Material</h1>", unsafe_allow_html=True)
    uploaded_pdfs = st.file_uploader("Choose syllabus files (PDF/PPT)", type=["pdf", "pptx", "ppt"], accept_multiple_files=True)
    
    if uploaded_pdfs:
        col_actions1, col_actions2 = st.columns(2)
        with col_actions1: extract_clicked = st.button("🚀 Extract & Merge Syllabus", type="primary")
        with col_actions2: regenerate_clicked = st.button("🔄 Regenerate Extraction")
            
        if extract_clicked or regenerate_clicked:
            with st.spinner("Extracting text and identifying units/topics from all PDFs..."):
                syllabi_drafts, raw_texts = [], []
                os.makedirs("temp", exist_ok=True)
                for idx, updf in enumerate(uploaded_pdfs):
                    # Keep original extension
                    ext = os.path.splitext(updf.name)[1]
                    tpath = os.path.join("temp", f"temp_syllabus_{idx}{ext}")
                    with open(tpath, "wb") as f: f.write(updf.getbuffer())
                    
                    from utils.pdf_parser import extract_text_from_file
                    etext = extract_text_from_file(tpath)
                    if etext:
                        raw_texts.append(f"--- Document {idx+1}: {updf.name} ---\n{etext}")
                        syllabi_drafts.append(parse_syllabus_topics(etext))
                    try: os.remove(tpath)
                    except: pass
                        
                if syllabi_drafts:
                    st.session_state["draft_syllabus"] = merge_syllabi(syllabi_drafts)
                    st.session_state["raw_extracted_text"] = "\n\n".join(raw_texts)
                    st.success(f"✅ Processed {len(uploaded_pdfs)} PDFs!")

    if "draft_syllabus" in st.session_state:
        draft = st.session_state["draft_syllabus"]
        st.markdown("### 📝 Review & Edit Extracted Syllabus")
        edited_units = []
        for u_idx, unit in enumerate(draft.get("units", [])):
            with st.expander(f"⚙️ {unit['unit_name']}", expanded=True):
                new_u = st.text_input(f"Unit {u_idx+1} Name", value=unit["unit_name"], key=f"edit_uname_{u_idx}")
                new_t = st.text_area(f"Topics in Unit {u_idx+1} (comma-separated)", value=", ".join(unit.get("topics", [])), key=f"edit_tops_{u_idx}")
                edited_units.append({"unit_name": new_u, "topics": [t.strip() for t in new_t.split(",") if t.strip()]})
                
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Save to Active Plan", type="primary"):
                update_syllabus({"reasoning": draft.get("reasoning", ""), "units": edited_units})
                st.session_state.pop("draft_syllabus", None)
                st.success("Syllabus saved!")
                st.rerun()

elif page == "Manual Topic Study":
    st.markdown("<h1>✍️ Manual Topic Study Setup</h1>", unsafe_allow_html=True)
    st.write("Manually configure your syllabus if you don't have a PDF available.")
    
    with st.form("manual_topics_form"):
        subject_name = st.text_input("Subject Name", value=profile.get("subject", ""))
        exam_date = st.date_input("Exam Date", value=datetime.strptime(profile["exam_date"], "%Y-%m-%d").date() if profile.get("exam_date") else date.today())
        study_hours = st.slider("Target Study Hours Per Day", 1, 12, int(profile.get("study_hours_per_day", 4)))
        
        st.markdown("### Syllabus Units")
        st.write("Define your units and topics. Separate topics with commas.")
        
        units_input = []
        for i in range(5): # Allow up to 5 units manually at once
            st.markdown(f"**Unit {i+1}**")
            u_name = st.text_input(f"Name for Unit {i+1}", key=f"m_u_{i}")
            u_tops = st.text_area(f"Topics for Unit {i+1}", key=f"m_t_{i}")
            if u_name or u_tops:
                units_input.append({"name": u_name, "topics": u_tops})
                
        if st.form_submit_button("Continue & Save Syllabus"):
            if not units_input:
                st.error("Please provide at least one Unit and Topic.")
            else:
                formatted_units = []
                for idx, u in enumerate(units_input):
                    uname = u["name"] if u["name"] else f"Unit {idx+1}"
                    t_list = [x.strip() for x in u["topics"].split(",") if x.strip()]
                    formatted_units.append({"unit_name": uname, "topics": t_list})
                    
                fullname = st.session_state.get("fullname", "Student")
                update_profile(fullname, profile.get("course", ""), subject_name, exam_date, study_hours, len(formatted_units), profile.get("semester", ""))
                update_syllabus({"reasoning": "Manual Input", "units": formatted_units})
                st.success("✅ Manual Syllabus saved! You can now use the Study Planner and Quiz Generator.")

elif page == "Study Planner":
    st.markdown("<h1>📅 AI Study Planner</h1>", unsafe_allow_html=True)
    if not syllabus.get("units"): st.warning("⚠️ Setup your syllabus first.")
    else:
        plan_scope = st.radio("Choose Planning Scope", ["Entire Syllabus", "Selected Units"])
        selected_units = None
        if plan_scope == "Selected Units":
            selected_units = st.multiselect("Select Units", [u["unit_name"] for u in syllabus.get("units", [])])
            
        if st.button("✨ Generate Study Plan", type="primary"):
            with st.spinner("Formulating timeline..."):
                try:
                    exam_date_str = profile.get("exam_date")
                    if not exam_date_str: exam_date_str = str(date.today())
                    
                    study_hours = profile.get("study_hours_per_day")
                    if not study_hours: study_hours = 4

                    res = StudyPlannerAgent().generate_plan(exam_date_str, syllabus["units"], study_hours, selected_units)
                    if res.get("success"):
                        save_study_plan(res.get("plan", []))
                        st.rerun()
                    else:
                        st.error(f"Failed to generate: {res.get('error', 'Unknown error')}")
                except Exception as e:
                    import traceback
                    st.error("Exception occurred during generation:")
                    st.exception(e)
                    st.code(traceback.format_exc())
                
        if study_plan:
            st.markdown("<h2>📋 Schedule</h2>", unsafe_allow_html=True)
            st.table([{"Day": f"Day {i['day']}", "Activity": i['task'], "Hours": f"{i['hours']} hrs"} for i in study_plan])

elif page == "Quiz Generator":
    st.markdown("<h1>📝 Quiz Generator</h1>", unsafe_allow_html=True)
    if not syllabus.get("units"): st.warning("⚠️ Setup your syllabus first.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            quiz_scope = st.selectbox("Select Scope", ["Specific Unit", "Multiple Units", "Entire Syllabus"])
            assessment_scope_desc, quiz_topics = "", []
            unit_names = [u["unit_name"] for u in syllabus.get("units", [])]
            
            if quiz_scope == "Specific Unit":
                chosen_unit = st.selectbox("Choose Unit", unit_names)
                assessment_scope_desc = chosen_unit
                quiz_topics = next((u["topics"] for u in syllabus["units"] if u["unit_name"] == chosen_unit), [])
            elif quiz_scope == "Multiple Units":
                chosen_units = st.multiselect("Choose Units", unit_names, default=unit_names[:1])
                assessment_scope_desc = " & ".join(chosen_units)
                for u in syllabus["units"]:
                    if u["unit_name"] in chosen_units: quiz_topics.extend(u["topics"])
            else:
                assessment_scope_desc = "Entire Syllabus"
                for u in syllabus["units"]: quiz_topics.extend(u["topics"])
                
        with c2:
            num_q = st.slider("Questions per section", 1, 5, 3)
            difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
            
        if st.button("🚀 Generate Assessment", type="primary"):
            with st.spinner("Generating..."):
                try:
                    res = QuizAgent().generate_quiz(assessment_scope_desc, num_q, difficulty, topics=quiz_topics)
                    if res.get("success"):
                        st.session_state["active_quiz"] = res["data"]
                        st.session_state["show_answers"] = False
                        st.rerun()
                    else:
                        st.error(f"Failed to generate quiz: {res.get('error', 'Unknown error')}")
                except Exception as e:
                    import traceback
                    st.error("Exception occurred during generation:")
                    st.exception(e)
                    st.code(traceback.format_exc())
                    
        if "active_quiz" in st.session_state:
            q = st.session_state["active_quiz"]
            st.markdown(f"## Practice Test: {q.get('topic', 'Quiz')}")
            for i, mcq in enumerate(q.get("multiple_choice", [])):
                st.write(f"**Q{i+1}: {mcq['question']}**")
                st.radio(f"Select answer", mcq["options"], key=f"q_{i}", index=None)
            
            if st.button("Submit Answers"): st.session_state["show_answers"] = True
            
            if st.session_state.get("show_answers"):
                st.markdown("### 🔑 Solutions")
                for i, mcq in enumerate(q.get("multiple_choice", [])):
                    st.markdown(f"**Q{i+1}:** {mcq['question']} -> `{mcq['correct_answer']}`")
                    
                st.markdown("#### 📥 Export Quiz")
                from utils.export_helper import export_quiz_pdf
                st.download_button("Download Quiz (PDF)", data=export_quiz_pdf(q), file_name="quiz.pdf", mime="application/pdf")

elif page == "AI Notes Generator":
    st.markdown("<h1>📚 AI Notes Generator</h1>", unsafe_allow_html=True)
    if not syllabus.get("units"): st.warning("⚠️ Setup your syllabus first.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            notes_scope = st.selectbox("Notes Scope", ["Single Topic", "Selected Units", "Entire Syllabus"])
            target_scope, notes_topics = "", []
            unit_names = [u["unit_name"] for u in syllabus.get("units", [])]
            
            if notes_scope == "Single Topic":
                selected_topic = st.selectbox("Select Topic", get_flat_topics())
                target_scope = selected_topic
                notes_topics = [selected_topic]
            elif notes_scope == "Selected Units":
                chosen_units = st.multiselect("Choose Units", unit_names, default=unit_names[:1] if unit_names else [])
                target_scope = " & ".join(chosen_units)
                for u in syllabus["units"]:
                    if u["unit_name"] in chosen_units: notes_topics.extend(u["topics"])
            else:
                target_scope = "Entire Syllabus"
                for u in syllabus["units"]: notes_topics.extend(u["topics"])
                
        with c2: 
            note_format = st.selectbox("Format", ["Short Notes", "Detailed Notes", "Important Exam Points"])
            
        if st.button("🚀 Generate Notes", type="primary"):
            cache_key = f"notes_{st.session_state.get('active_plan_id', 'unknown')}_{target_scope}_{note_format}"
            if cache_key in st.session_state:
                st.session_state["active_notes"] = st.session_state[cache_key]
                st.success("Loaded notes from cache!")
            else:
                progress_placeholder = st.empty()
                def progress_cb(msg):
                    progress_placeholder.info(msg)
                    
                with st.spinner("Compiling notes..."):
                    try:
                        res = NotesAgent().generate_notes(
                            target_scope, 
                            note_format, 
                            json.dumps(syllabus.get("units", [])),
                            topics=notes_topics,
                            progress_callback=progress_cb
                        )
                        progress_placeholder.empty()
                        if res.get("success"):
                            st.session_state["active_notes"] = res["notes"]
                            st.session_state[cache_key] = res["notes"]
                        else:
                            st.error(f"Failed to generate notes: {res.get('error', 'Unknown error')}")
                    except Exception as e:
                        progress_placeholder.empty()
                        import traceback
                        st.error("Exception occurred during generation:")
                        st.exception(e)
                        st.code(traceback.format_exc())
                
        if "active_notes" in st.session_state:
            st.markdown(st.session_state["active_notes"])
            
            st.markdown("#### 📥 Export Notes")
            from utils.export_helper import export_notes_pdf
            notes_md = st.session_state["active_notes"]
            dl_c1, dl_c2 = st.columns(2)
            dl_c1.download_button("Download Markdown (.md)", data=notes_md, file_name="notes.md", mime="text/markdown")
            dl_c2.download_button("Download PDF", data=export_notes_pdf(notes_md), file_name="notes.pdf", mime="application/pdf")

elif page == "AI Study Assistant":
    st.markdown("<h1>💬 AI Study Assistant</h1>", unsafe_allow_html=True)
    if not syllabus.get("units"): st.warning("⚠️ Setup your syllabus first.")
    else:
        # Debug Panel
        with st.expander("🛠️ Developer Debug Panel"):
            st.write(f"**HAS_REAL_KEY:** {HAS_REAL_KEY}")
            st.write(f"**API Available:** {is_api_available()}")
            st.write(f"**Current Model:** gemini-2.5-flash")
            
        chat_history = state.get("chat_history", [])
        
        # Display existing chat history
        for msg in chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        # Chat input
        if prompt := st.chat_input("Ask a question about your study plan or syllabus..."):
            with st.chat_message("user"):
                st.markdown(prompt)
                
            chat_history.append({"role": "user", "content": prompt})
            
            # Save so the assistant has access if it crashes/refreshes
            from utils.storage import save_chat_history
            save_chat_history(chat_history)
            
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        # Build context
                        ft = get_flat_topics()
                        progress_pct = int((len(completed_topics) / len(ft)) * 100) if ft else 0
                        
                        weak_topics = []
                        if "recs_data" in st.session_state:
                            recs = st.session_state["recs_data"].get("recommendations", [])
                            # Just a naive heuristic for this demo
                            weak_topics = [t for t in ft if any(t.lower() in r.get("text", "").lower() for r in recs)]
                            
                        context_data = {
                            "subject": profile.get("subject", "Unknown"),
                            "progress_pct": progress_pct,
                            "completed_topics": completed_topics,
                            "weak_topics": weak_topics,
                            "syllabus_units": syllabus.get("units", []),
                            "study_plan": study_plan,
                            "raw_text": st.session_state.get("raw_extracted_text", "")
                        }
                        
                        res = AssistantAgent().generate_response(prompt, chat_history[:-1], context_data)
                        
                        if res.get("success"):
                            if res.get("quota_exceeded"):
                                st.warning("⚠️ Gemini quota exceeded. Switching to offline AI mode.")
                            
                            badge = "🟡 Offline AI (Mock)" if res.get("is_mock") else "🟢 Gemini API"
                            
                            st.markdown(res["response"])
                            st.caption(f"*Source: {badge}*")
                            
                            with st.expander("🔍 AI Reasoning & Context"):
                                st.write(res["reasoning"])
                                st.write(f"**Response Source:** {badge}")
                            
                            chat_history.append({"role": "assistant", "content": res["response"]})
                            save_chat_history(chat_history)
                        else:
                            st.error("Failed to generate response. Check Developer Debug Panel for details.")
                            with st.expander("🛠️ Error Details"):
                                st.code(res.get("error", "Unknown Error"))
                    except Exception as e:
                        import traceback
                        st.error("Exception occurred:")
                        st.exception(e)
                        st.code(traceback.format_exc())

elif page == "Progress Tracker":
    st.markdown("<h1>📊 Progress Tracker</h1>", unsafe_allow_html=True)
    if not syllabus.get("units"): st.warning("⚠️ Setup your syllabus first.")
    else:
        ft = get_flat_topics()
        progress = int((len(completed_topics) / len(ft)) * 100) if ft else 0
        st.write(f"### Readiness: {progress}%")
        st.progress(progress / 100)
        
        for u_idx, u in enumerate(syllabus["units"]):
            st.markdown(f"**{u['unit_name']}**")
            for t_idx, t in enumerate(u["topics"]):
                tid = f"{u['unit_name']} - {t}"
                val = st.checkbox(t, value=tid in completed_topics, key=f"c_{u_idx}_{t_idx}_{tid}")
                if val and tid not in completed_topics:
                    toggle_topic_status(tid, True)
                    st.rerun()
                elif not val and tid in completed_topics:
                    toggle_topic_status(tid, False)
                    st.rerun()

elif page == "Recommendations":
    st.markdown("<h1>✨ AI Recommendation Agent</h1>", unsafe_allow_html=True)
    if not syllabus.get("units"): st.warning("⚠️ Setup your syllabus first.")
    else:
        if st.button("⚡ Get Latest Recommendations", type="primary"):
            with st.spinner("Analyzing..."):
                try:
                    exam_date_str = profile.get("exam_date")
                    if not exam_date_str: exam_date_str = str(date.today())
                    
                    study_hours = profile.get("study_hours_per_day")
                    if not study_hours: study_hours = 4

                    res = RecommendationAgent().generate_recommendations(exam_date_str, syllabus["units"], completed_topics, study_hours)
                    if res.get("success"):
                        st.session_state["recs_data"] = res
                    else:
                        st.error(f"Failed to generate recommendations: {res.get('error', 'Unknown error')}")
                except Exception as e:
                    import traceback
                    st.error("Exception occurred during generation:")
                    st.exception(e)
                    st.code(traceback.format_exc())
                    
        if "recs_data" in st.session_state:
            res = st.session_state["recs_data"]
            for item in res.get("recommendations", []):
                st.markdown(f"**[{item.get('priority')}]** {item['text']}")

elif page == "🔌 MCP Developer Panel":
    st.title("🔌 MCP Developer Panel")
    st.markdown("This panel monitors the official **Model Context Protocol (MCP)** integration.")
    
    try:
        from utils.mcp_client import execute_mcp_tool
        
        # We perform a lightweight ping to the MCP server. 
        # Using an empty topics list.
        test_res = execute_mcp_tool("view_progress", {"completed_topics_json": "[]", "flat_topics_json": "[]"})
        
        # Display the connection status cleanly
        if test_res.get("status") == "success":
            st.success("✅ MCP Server Status: Connected")
            st.info("Execution Mode: Official MCP")
        else:
            st.error(f"❌ MCP Server Status: Not Connected (Error: {test_res.get('message', 'Unknown Error')})")
            st.warning("Execution Mode: Running in Local Fallback Mode")
            
        # Display MCP Server Info
        st.subheader("Server Information")
        col1, col2, col3 = st.columns(3)
        col1.metric("SDK", "mcp Python SDK")
        col2.metric("Transport", "stdio")
        col3.metric("Server Name", "StudyPlannerMCP")
            
        st.subheader("Registered MCP Tools")
        st.markdown("- `generate_study_plan`\n- `generate_quiz`\n- `generate_ai_notes`\n- `explain_topic`\n- `search_syllabus`\n- `view_progress`\n- `generate_recommendations`")
        
        st.subheader("Recent MCP Tool Calls")
        import os, json
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, "data", "mcp_history.json")
        
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            if history:
                # Last Tool Request / Response
                last_call = history[-1]
                st.markdown("### Last Tool Request & Response")
                col_req, col_res = st.columns(2)
                with col_req:
                    with st.expander("Last Request", expanded=True):
                        st.write(f"**Tool:** `{last_call.get('tool')}`")
                        st.json(last_call.get('arguments', {}))
                with col_res:
                    with st.expander("Last Response", expanded=True):
                        if last_call.get('status') == 'success':
                            st.json(last_call.get('response', {}))
                        else:
                            st.error(last_call.get('error', 'Unknown Error'))
                
                st.markdown("---")
                
                # Render the rest of the history
                st.markdown("### Full Tool Call History")
                for entry in reversed(history):
                    status_icon = "✅ Success" if entry.get("status") == "success" else "❌ Failed"
                    with st.expander(f"{status_icon} | {entry.get('timestamp', '')} | {entry.get('tool')}"):
                        st.json(entry)
            else:
                st.info("No MCP calls have been made yet.")
        else:
            st.info("No MCP calls have been made yet.")
            
    except Exception as e:
        import traceback
        st.error("An error occurred while loading the MCP Developer Panel.")
        st.exception(e)
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
