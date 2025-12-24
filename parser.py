# parser.py – FINAL UPDATED VERSION (with duplicate-word removal)

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
import fitz  # PyMuPDF
from docx import Document

# -----------------------------
# Duplicate Word Removal
# -----------------------------
def remove_duplicate_words(text: str) -> str:
    if not isinstance(text, str):
        return text
    words = text.split()
    seen = []
    out = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.append(lw)
            out.append(w)
    return " ".join(out)

# -----------------------------
# Section Header Definitions
# -----------------------------
SECTION_HEADERS_EN = [
    "education", "experience", "work experience", "projects", "project",
    "skills", "certifications", "summary", "objective", "contact",
    "achievements", "technical skills", "soft skills"
]

SECTION_HEADERS_KN = ["ಶಿಕ್ಷಣ", "ಅನುಭವ", "ಪ್ರಾಜೆಕ್ಟ್", "ಕೌಶಲ್ಯ", "ಸಾರಾಂಶ", "ಸಂಪರ್ಕ"]

# -----------------------------
# File Loading
# -----------------------------
def load_text(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        with fitz.open(file_path) as doc:
            return "\n".join(page.get_text() for page in doc)
    elif ext == ".docx":
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return file_path.read_text(encoding="utf-8", errors="ignore")

def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def is_kannada(text: str) -> bool:
    return bool(re.search(r"[\u0C80-\u0CFF]", text))

# -----------------------------
# Name Extraction
# -----------------------------
def extract_name(text: str) -> Tuple[str, float]:
    lines = [l for l in text.splitlines()[:30] if l.strip()]
    seen = set()

    for line in lines:
        line = re.sub(r'[|•*►◆−–—-]', ' ', line)
        line = re.sub(r'\s{2,}', ' ', line).strip(" .,|-–—()[]{}")

        if not line or len(line) < 5:
            continue

        if any(kw in line.lower() for kw in [
            "email", "phone", "linkedin", "github", "cgpa", "education",
            "skills", "project", "experience"
        ]):
            continue

        candidates = [c.strip() for c in re.split(r'\s{4,}|\t+', line) if c.strip()]

        for name in candidates:
            words = name.split()
            if len(words) < 2 or len(words) > 5:
                continue

            lower_name = name.lower()
            if lower_name in seen:
                continue

            if re.match(r"^[A-Z][A-Za-z'.-]+\s+[A-Z][A-Za-z'.-]+", name):
                seen.add(lower_name)
                return name, 0.99

            if all(w and w[0].isupper() for w in words):
                seen.add(lower_name)
                return name, 0.97

    email = re.search(r"([a-zA-Z]+)[\._]?([a-zA-Z]+)?@", text)
    if email:
        n = f"{email.group(1).title()} {email.group(2).title() if email.group(2) else ''}".strip()
        return n, 0.85

    return "Unknown", 0.1

# -----------------------------
# Contact Extraction
# -----------------------------
def extract_contacts(text: str) -> Tuple[Dict[str, str], float]:
    phone = re.search(r"(\+91[- ]?)?[6-9]\d{9}", text)
    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    linkedin = re.search(r"(linkedin\.com/in/[A-Za-z0-9\-_]+)", text, re.I)
    github = re.search(r"(github\.com/[A-Za-z0-9\-_]+)", text, re.I)

    out = {}
    score = 0.0

    if phone: out["phone"] = phone.group(0); score += 0.35
    if email: out["email"] = email.group(0); score += 0.35
    if linkedin: out["linkedin"] = linkedin.group(1); score += 0.2
    if github: out["github"] = github.group(1); score += 0.2

    return out, min(score, 0.99)

# -----------------------------
# Skills
# -----------------------------
def load_skills_dict(skills_path: Path) -> List[str]:
    try:
        return json.loads(skills_path.read_text())
    except:
        return ["python", "java", "react", "django", "flask", "aws", "docker"]

def extract_skills(text: str, skills_list: List[str]) -> Tuple[List[str], float]:
    found = set()
    low = text.lower()
    for skill in skills_list:
        if re.search(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])", low):
            found.add(skill.title())
    score = 0.1 if not found else min(0.3 + 0.7 * len(found) / max(1, len(skills_list)//5), 0.98)
    return sorted(found), score

# -----------------------------
# CGPA
# -----------------------------
def extract_cgpa(text: str) -> Tuple[str, float]:
    patterns = [
        r"CGPA.*?(\d+\.\d{1,2})",
        r"GPA.*?(\d+\.\d{1,2})",
        r"(\d+\.\d{1,2})\s*/\s*10",
        r"(\d+\.\d{1,2})\s*out\s*of\s*10"
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1), 0.99
    return "", 0.0

# ------------------------------------------------
# Project Extraction
# ------------------------------------------------
def extract_projects(text: str) -> Tuple[List[str], float]:
    projects = []

    sec = re.search(
        r"(?si)(projects?|project details)\s*[:\-]?\s*(.+?)(\n[A-Z][A-Za-z ]{3,}|$)",
        text
    )
    if sec:
        block = sec.group(2)
        lines = [l.strip() for l in block.split("\n") if len(l.strip()) > 2]

        combined = []
        current_title = ""

        for line in lines:
            if line.isupper():
                continue

            if re.match(r"^[A-Za-z].{4,}", line) and not line.startswith(("•", "-", "*", "• ", "1.", "2.")):
                current_title = line
                combined.append([line])
                continue

            if current_title and (line.startswith(("•", "-", "*")) or len(line.split()) > 3):
                combined[-1].append(line)

        for c in combined:
            title = c[0]
            desc = "; ".join([d.lstrip("•-* ") for d in c[1:]])
            if desc:
                projects.append(f"{title} – {desc}")
            else:
                projects.append(title)

    numbered = re.findall(r"(?m)^\s*(\d+\.|\(\d+\))\s*(.+)", text)
    for _, title in numbered:
        title = title.strip()
        pattern = rf"{re.escape(title)}\s*\n(.+?)(\n\d+\.|\n[A-Z ]{{3,}}|$)"
        desc = re.search(pattern, text, re.S)
        if desc:
            block = desc.group(1).strip()
            block = re.sub(r"\n{1,2}", " ", block)
            projects.append(f"{title} – {block}")
        else:
            projects.append(title)

    bullets = re.findall(r"(?m)^\s*[-•*]\s*(.+)", text)
    for b in bullets:
        if len(b) > 5:
            projects.append(b.strip())

    final = []
    for p in projects:
        p = p.strip(" .-_")
        if len(p) > 5 and p not in final:
            final.append(p)

    return final[:10], (0.9 if final else 0.0)

# ------------------------------------------------
# Experience (simplified)
# ------------------------------------------------
def extract_experience(text: str) -> Tuple[List[Dict], float]:
    return [], 0.0

def section_confidence_map(d: Dict[str, float]) -> Dict[str, int]:
    return {k: int(round(v * 100)) for k, v in d.items()}

# ------------------------------------------------
# Parse a Single File
# ------------------------------------------------
def parse_file(path: Path, skills_path: Path) -> Dict:
    raw = load_text(path)
    text = clean_text(raw)
    skills_list = load_skills_dict(skills_path)

    name, c_name = extract_name(text)
    name = remove_duplicate_words(name)           # 🔥 FIX DUPLICATE NAMES

    contacts, c_contact = extract_contacts(text)

    skills, c_skills = extract_skills(text, skills_list)
    skills = list(dict.fromkeys(skills))          # 🔥 FIX DUP SKILLS

    cgpa, c_cgpa = extract_cgpa(text)

    projects, c_proj = extract_projects(text)
    projects = [remove_duplicate_words(p) for p in projects]  # 🔥 FIX DUP PROJECT TITLES

    education = ""
    experience, c_exp = extract_experience(text)

    conf = section_confidence_map({
        "name": c_name, "contact": c_contact, "skills": c_skills,
        "education": 0.5, "cgpa": c_cgpa,
        "projects": c_proj, "experience": c_exp
    })

    return {
        "file": path.name,
        "name": name,
        "contacts": contacts,
        "skills": skills,
        "cgpa": cgpa,
        "projects": projects,
        "projects_text": " ".join(projects),
        "experience": experience,
        "confidence": conf,
        "language": "Kannada" if is_kannada(text) else "English",
        "raw_text": text
    }

# ------------------------------------------------
# Parse an Entire Folder
# ------------------------------------------------
def parse_folder(folder: Path, skills_path: Path) -> pd.DataFrame:
    records = []
    for p in folder.glob("*"):
        if p.suffix.lower() in (".pdf", ".docx", ".txt"):
            try:
                records.append(parse_file(p, skills_path))
            except Exception as e:
                records.append({"file": p.name, "error": str(e)})
    return pd.DataFrame(records)
