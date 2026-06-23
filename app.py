from flask import Flask, render_template, request, jsonify
import anthropic
import json
import re
import os
import uuid
from datetime import datetime

# Load .env if present
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
DATA_FILE = "data/lessons.json"

def load_lessons():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_lessons(lessons):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)

def extract_json_from_response(text):
    """Try multiple strategies to extract a JSON object from Claude's response."""
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Find the outermost {...} block
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None

def extract_text_from_file(file):
    filename = file.filename.lower()
    if filename.endswith(".pdf"):
        import fitz
        data = file.read()
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    elif filename.endswith(".docx"):
        from docx import Document
        import io
        doc = Document(io.BytesIO(file.read()))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif filename.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore")
    else:
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/lessons", methods=["GET"])
def get_lessons():
    lessons = load_lessons()
    return jsonify([{"id": l["id"], "title": l["title"], "course": l["course"], "date": l["date"]} for l in lessons])

@app.route("/api/lessons/<lesson_id>", methods=["GET"])
def get_lesson(lesson_id):
    lessons = load_lessons()
    lesson = next((l for l in lessons if l["id"] == lesson_id), None)
    if not lesson:
        return jsonify({"error": "לא נמצא"}), 404
    return jsonify(lesson)

@app.route("/api/lessons/<lesson_id>", methods=["DELETE"])
def delete_lesson(lesson_id):
    lessons = load_lessons()
    lessons = [l for l in lessons if l["id"] != lesson_id]
    save_lessons(lessons)
    return jsonify({"ok": True})

@app.route("/api/upload", methods=["POST"])
def upload_file():
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "לא נבחרו קבצים"}), 400

    combined_parts = []
    filenames = []
    errors = []

    for file in files:
        if file.filename == "":
            continue
        text = extract_text_from_file(file)
        if text is None:
            errors.append(f"{file.filename}: סוג קובץ לא נתמך")
            continue
        if len(text.strip()) < 10:
            errors.append(f"{file.filename}: קובץ ריק")
            continue
        combined_parts.append(f"=== {file.filename} ===\n{text}")
        filenames.append(file.filename)

    if not combined_parts:
        return jsonify({"error": "לא ניתן לקרוא אף קובץ. " + "; ".join(errors)}), 400

    combined_text = "\n\n".join(combined_parts)
    if len(combined_text.strip()) < 50:
        return jsonify({"error": "החומר קצר מדי"}), 400

    return jsonify({
        "text": combined_text,
        "filenames": filenames,
        "errors": errors
    })

@app.route("/api/generate/summary", methods=["POST"])
def generate_summary():
    data = request.json
    text = data.get("text", "").strip()
    summary_type = data.get("summary_type", "מפורט ומסודר")
    course = data.get("course", "")
    title = data.get("title", "שיעור")
    filenames = data.get("filenames", [])

    if not text or len(text) < 50:
        return jsonify({"error": "החומר קצר מדי"}), 400

    file_count = len(filenames) if filenames else text.count("=== ")
    file_list = "\n".join(f"- {f}" for f in filenames) if filenames else ""
    files_instruction = f"""החומר מכיל {file_count} קבצים:
{file_list}
חובה לכסות את כל הנושאים מכל אחד מהקבצים הללו. אל תדלג על קובץ אחד.""" if file_count > 1 else ""

    # Scale max_tokens with content size: base 3000, +1000 per extra file, cap at 8000
    max_tokens = min(8000, 3000 + max(0, file_count - 1) * 1000)

    prompt = f"""אתה עוזר לימודי מומחה. כתוב סיכום מקיף ומפורט של חומר הלימוד הבא בעברית.

{files_instruction}

דרישות חובה:
- הסיכום חייב להיות ארוך ומפורט — לפחות עמוד אחד מלא של טקסט (אם יש יותר חומר, כתוב יותר)
- כסה את כל הנושאים, ההגדרות, הרעיונות המרכזיים והפרטים החשובים
- לכל נושא: הסבר מלא, לא רק כותרת
- אל תקצר — עדיף יותר מדי מדי מעט
- השתמש אך ורק במה שמופיע בטקסט

סוג סיכום: {summary_type}

מבנה:
# כותרת ראשית

## נושא 1
[הסבר מפורט, הגדרות, נקודות מפתח]

## נושא 2
[הסבר מפורט...]

(המשך לכל הנושאים בחומר)

## מושגי מפתח לזכור
[רשימה מפורטת של כל המונחים המרכזיים עם הגדרה קצרה לכל אחד]

חומר הלימוד:
{text}"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    summary = message.content[0].text

    lessons = load_lessons()
    lesson_id = str(uuid.uuid4())[:8]
    lesson = {
        "id": lesson_id,
        "title": title or "שיעור ללא שם",
        "course": course or "כללי",
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "text": text,
        "summary": summary,
        "quiz": None,
        "chat_history": []
    }
    lessons.append(lesson)
    save_lessons(lessons)
    return jsonify({"summary": summary, "lesson_id": lesson_id})

@app.route("/api/generate/quiz", methods=["POST"])
def generate_quiz():
    data = request.json
    lesson_id = data.get("lesson_id")
    q_count = data.get("q_count", 10)
    difficulty = data.get("difficulty", "בינוני")

    lessons = load_lessons()
    lesson = next((l for l in lessons if l["id"] == lesson_id), None)
    if not lesson:
        return jsonify({"error": "שיעור לא נמצא"}), 404
    text = lesson["text"]

    prompt = f"""אתה עוזר לימודי. צור {q_count} שאלות אמריקאיות בעברית המבוססות אך ורק על הטקסט הבא.

חשוב מאוד:
- אל תמציא עובדות או מידע שאינו מופיע בטקסט
- רמת קושי: {difficulty}
- כל שאלה עם 4 תשובות אפשריות
- רק תשובה אחת נכונה
- הוסף הסבר קצר לתשובה הנכונה מתוך החומר

החזר JSON בלבד, ללא טקסט נוסף:
{{"questions":[{{"q":"שאלה","options":["א. תשובה1","ב. תשובה2","ג. תשובה3","ד. תשובה4"],"correct":0,"explanation":"הסבר"}}]}}

חומר הלימוד:
{text}"""

    message = client.messages.create(model="claude-opus-4-6", max_tokens=4000,
        messages=[{"role": "user", "content": prompt}])
    quiz = extract_json_from_response(message.content[0].text)
    if quiz is None:
        return jsonify({"error": "שגיאה בפענוח תשובת ה-AI. נסי שוב."}), 500

    for l in lessons:
        if l["id"] == lesson_id:
            l["quiz"] = quiz
            break
    save_lessons(lessons)
    return jsonify(quiz)

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    lesson_id = data.get("lesson_id")
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "שאלה ריקה"}), 400

    lessons = load_lessons()
    lesson = next((l for l in lessons if l["id"] == lesson_id), None)
    if not lesson:
        return jsonify({"error": "שיעור לא נמצא"}), 404

    history = lesson.get("chat_history", [])
    messages = []
    for h in history[-6:]:
        messages.append({"role": "user", "content": h["q"]})
        messages.append({"role": "assistant", "content": h["a"]})
    messages.append({"role": "user", "content": question})

    # Use summary as context; fall back to truncated raw text if no summary yet
    context = lesson.get("summary") or lesson["text"]
    words = context.split()
    if len(words) > 3000:
        context = " ".join(words[:3000]) + "\n[...]"

    system = f"""אתה עוזר לימודי. ענה על שאלות הסטודנטית אך ורק על בסיס חומר הלימוד הבא.
אם השאלה לא קשורה לחומר — אמור זאת בכנות.
ענה בעברית, בצורה ברורה ומסודרת.

חומר הלימוד:
{context}"""

    response = client.messages.create(model="claude-opus-4-6", max_tokens=1000,
        system=system, messages=messages)
    answer = response.content[0].text

    history.append({"q": question, "a": answer, "time": datetime.now().strftime("%H:%M")})
    for l in lessons:
        if l["id"] == lesson_id:
            l["chat_history"] = history
            break
    save_lessons(lessons)
    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(debug=True, port=5050)
