import csv
import io
import json
from fpdf import FPDF

def sanitize_pdf_text(text):
    """
    Removes characters that are not supported by the default latin-1
    encoding used by fpdf2's core fonts (like Helvetica).
    Replaces common smart quotes and dashes with ascii equivalents.
    """
    if not isinstance(text, str):
        return str(text)
        
    replacements = {
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '—': '-', '–': '-', '…': '...', '•': '*',
        '✅': '[v]', '❌': '[x]', '⭐': '*', '🔹': '*', '📚': ''
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
        
    return text.encode('latin-1', 'ignore').decode('latin-1').strip()

def export_plan_csv(study_plan):
    """
    Exports the study plan to a CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Day", "Task", "Hours", "Topics"])
    for day in study_plan:
        writer.writerow([day.get("day", ""), day.get("task", ""), day.get("hours", ""), ", ".join(day.get("topics", []))])
    return output.getvalue()

def export_plan_pdf(study_plan):
    """
    Exports the study plan to a PDF bytes object.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=16, style="B")
    pdf.cell(0, 10, sanitize_pdf_text("Study Plan Schedule"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    for day in study_plan:
        pdf.set_font("helvetica", size=12, style="B")
        pdf.cell(0, 10, sanitize_pdf_text(f"Day {day.get('day', '')} - {day.get('hours', '')} hours"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", size=12)
        pdf.multi_cell(0, 10, sanitize_pdf_text(f"Task: {day.get('task', '')}"), new_x="LMARGIN", new_y="NEXT")
        topics = ", ".join(day.get("topics", []))
        if topics:
            pdf.multi_cell(0, 8, sanitize_pdf_text(f"Topics: {topics}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
    return bytes(pdf.output())

def export_quiz_pdf(quiz_data):
    """
    Exports the quiz to a PDF bytes object.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=16, style="B")
    pdf.cell(0, 10, sanitize_pdf_text(f"Quiz: {quiz_data.get('topic', 'Assessment')}"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("helvetica", size=10, style="I")
    pdf.cell(0, 10, sanitize_pdf_text(f"Difficulty: {quiz_data.get('difficulty', 'Mixed')}"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    # Questions
    pdf.set_font("helvetica", size=14, style="B")
    pdf.cell(0, 10, sanitize_pdf_text("Questions"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=12)
    
    for i, mcq in enumerate(quiz_data.get("multiple_choice", [])):
        pdf.set_font("helvetica", size=12, style="B")
        pdf.multi_cell(0, 8, sanitize_pdf_text(f"Q{i+1}: {mcq.get('question', '')}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", size=12)
        for opt in mcq.get("options", []):
            pdf.multi_cell(0, 8, f"  [ ] {sanitize_pdf_text(opt)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        
    # Answer Key
    pdf.add_page()
    pdf.set_font("helvetica", size=16, style="B")
    pdf.cell(0, 10, sanitize_pdf_text("Answer Key"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("helvetica", size=12)
    for i, mcq in enumerate(quiz_data.get("multiple_choice", [])):
        pdf.multi_cell(0, 10, sanitize_pdf_text(f"Q{i+1}: {mcq.get('correct_answer', '')}"), new_x="LMARGIN", new_y="NEXT")
        
    return bytes(pdf.output())

def export_notes_pdf(markdown_content):
    """
    Exports markdown notes to a simple text-based PDF bytes object.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    lines = markdown_content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            pdf.ln(5)
            continue
            
        if line.startswith('#'):
            level = len(line.split(' ')[0])
            # Remove the hashes
            text = line.lstrip('#').strip()
            # Clean some markdown formatting like ** or *
            text = text.replace('**', '').replace('*', '')
            pdf.set_font("helvetica", size=max(18 - (level * 2), 12), style="B")
            pdf.multi_cell(0, 10, sanitize_pdf_text(text), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", size=12)
        elif line.startswith('>'):
            pdf.set_font("helvetica", size=12, style="I")
            pdf.set_text_color(100, 100, 100)
            text = line.lstrip('>').strip()
            pdf.multi_cell(0, 8, sanitize_pdf_text(text), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", size=12)
            pdf.set_text_color(0, 0, 0)
        elif line.startswith('-') or line.startswith('*'):
            pdf.set_font("helvetica", size=12)
            text = line.lstrip('-*').strip()
            text = text.replace('**', '').replace('*', '')
            pdf.multi_cell(0, 8, f"  o {sanitize_pdf_text(text)}", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("helvetica", size=12)
            # Remove bold/italic asterisks just in case for plain text readability
            text = line.replace('**', '').replace('*', '')
            pdf.multi_cell(0, 8, sanitize_pdf_text(text), new_x="LMARGIN", new_y="NEXT")
            
    return bytes(pdf.output())
