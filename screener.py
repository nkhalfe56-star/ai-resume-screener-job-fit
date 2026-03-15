import re
import os
from typing import Optional
import pdfplumber
from sentence_transformers import SentenceTransformer, util
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
import tempfile

app = FastAPI(title="Resume Screener & Job Fit API", version="1.0")

# ── Config ─────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
model = SentenceTransformer(EMBEDDING_MODEL)

SKILL_KEYWORDS = [
    "python", "machine learning", "deep learning", "nlp", "pytorch", "tensorflow",
    "langchain", "fastapi", "sql", "pandas", "numpy", "scikit-learn",
    "transformers", "llm", "rag", "data analysis", "computer vision",
    "git", "docker", "aws", "react", "node.js",
]


# ── Helpers ──────────────────────────────────────────────────────────────────
def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def extract_skills(text: str) -> list[str]:
    text_lower = text.lower()
    found = [skill for skill in SKILL_KEYWORDS if skill in text_lower]
    return found


def compute_fit_score(resume_text: str, job_description: str) -> float:
    resume_emb = model.encode(resume_text, convert_to_tensor=True)
    jd_emb = model.encode(job_description, convert_to_tensor=True)
    score = float(util.cos_sim(resume_emb, jd_emb)[0][0])
    return round(score * 100, 2)  # percentage


def generate_feedback(score: float, matched_skills: list, jd: str) -> str:
    jd_lower = jd.lower()
    missing = [s for s in SKILL_KEYWORDS if s in jd_lower and s not in matched_skills]
    feedback_parts = []
    if score >= 75:
        feedback_parts.append("Strong match for this role.")
    elif score >= 50:
        feedback_parts.append("Moderate match - some alignment with job requirements.")
    else:
        feedback_parts.append("Low match - significant skill gaps detected.")
    if missing:
        feedback_parts.append(f"Consider adding: {', '.join(missing[:5])}.")
    return " ".join(feedback_parts)


# ── API ───────────────────────────────────────────────────────────────────────
class ScreeningResult(BaseModel):
    fit_score: float
    matched_skills: list[str]
    feedback: str
    recommendation: str


@app.post("/screen", response_model=ScreeningResult)
async def screen_resume(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    # Save uploaded PDF to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await resume.read())
        tmp_path = tmp.name

    try:
        resume_text = extract_text_from_pdf(tmp_path)
    finally:
        os.unlink(tmp_path)

    matched_skills = extract_skills(resume_text)
    fit_score = compute_fit_score(resume_text, job_description)
    feedback = generate_feedback(fit_score, matched_skills, job_description)
    recommendation = "Shortlist" if fit_score >= 65 else "Review" if fit_score >= 45 else "Reject"

    return ScreeningResult(
        fit_score=fit_score,
        matched_skills=matched_skills,
        feedback=feedback,
        recommendation=recommendation,
    )


@app.get("/health")
def health():
    return {"status": "ok", "model": EMBEDDING_MODEL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
