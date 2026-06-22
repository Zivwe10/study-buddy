# 📚 Study Buddy

כלי לימוד חכם — סיכומים ומבחנים אמריקאים מחומר השיעור שלך.

## הרצה מהירה

```bash
# 1. התקני dependencies
pip install -r requirements.txt

# 2. הגדירי API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. הריצי
python app.py
```

פתחי דפדפן בכתובת: http://localhost:5050

## מה יש כאן

- **סיכום** — מחולל סיכום מפורט מחומר השיעור בלבד
- **מבחן אמריקאי** — שאלות + משוב מיידי + הסבר
- **שאל שאלה** — צ'אט על החומר, עונה רק ממה שהזנת
- **היסטוריה** — כל השיעורים שמורים ב-`data/lessons.json`

## מבנה הפרויקט

```
study-buddy/
├── app.py              ← Flask backend
├── requirements.txt
├── templates/
│   └── index.html      ← כל ה-UI
└── data/
    └── lessons.json    ← נוצר אוטומטית
```
