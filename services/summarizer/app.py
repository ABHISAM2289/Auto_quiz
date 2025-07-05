from flask import Flask, request, jsonify, render_template_string, send_file
import requests
import google.generativeai as genai
import io

app = Flask(__name__)

genai.configure(api_key="AIzaSyBBGllnIZdo11cUjURk7d3V46xqgYmjIWc")

SPEECH_TO_TEXT_API = "http://127.0.0.1:5001/latest_transcript"

latest_summary_text = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Auto Summary</title>
    <style>
        body {
            min-height: 100vh;
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #333;
            background: linear-gradient(135deg, #fbc2eb 0%, #a6c1ee 50%, #fdcbf1 100%);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .main-card {
            background: rgba(255,255,255,0.97);
            border-radius: 22px;
            box-shadow: 0 8px 32px rgba(106,17,203,0.13), 0 1.5px 8px rgba(252,182,159,0.08);
            max-width: 650px;
            width: 96vw;
            margin: 40px 0;
            padding: 40px 36px 36px 36px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        h1 {
            color: #6a11cb;
            margin-bottom: 20px;
            letter-spacing: 1.5px;
            text-align: center;
            font-size: 2.2rem;
            font-weight: 800;
            text-shadow: 1px 2px 8px #e0e0ff;
        }
        form {
            margin: 18px 0 28px 0;
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        textarea {
            width: 100%;
            min-height: 80px;
            padding: 10px;
            margin-bottom: 18px;
            border-radius: 10px;
            border: 1.5px solid #ccc;
            font-size: 1rem;
            resize: vertical;
        }
        button {
            padding: 12px 32px;
            font-size: 1.1rem;
            background: linear-gradient(90deg, #6a11cb 0%, #2575fc 100%);
            color: #fff;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
            box-shadow: 0 2px 8px rgba(106,17,203,0.08);
        }
        button:hover {
            background: linear-gradient(90deg, #2575fc 0%, #6a11cb 100%);
            transform: translateY(-2px) scale(1.03);
        }
        .summary-container {
            width: 100%;
            background: linear-gradient(90deg, #f7fafd 60%, #e0c3fc 100%);
            padding: 26px 22px;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(44,62,80,0.07);
            text-align: left;
            white-space: pre-wrap;
            margin-top: 16px;
            border: 1.5px solid #e0e0e0;
        }
        h2 {
            color: #34495e;
            margin-top: 0;
        }
        a.download-btn button {
            margin-top: 12px;
            background: linear-gradient(90deg, #ff758c 0%, #ff7eb3 100%);
        }
        a.download-btn button:hover {
            background: linear-gradient(90deg, #ff7eb3 0%, #ff758c 100%);
        }
        @media (max-width: 700px) {
            .main-card {
                padding: 18px 4vw;
            }
            .summary-container {
                padding: 14px 6px;
            }
        }
    </style>
</head>
<body>
    <div class="main-card">
        <h1>📝 Summary</h1>
        <form method="POST">
            <textarea name="custom_prompt" placeholder="Enter your custom prompt here... (Optional)"></textarea>
            <button type="submit">Generate Summary</button>
        </form>

        {% if summary %}
        <div class="summary-container">
            <h2>Summary:</h2>
            <div>{{ summary }}</div>
            <a href="/download_summary" class="download-btn">
                <button type="button">📥 Download Summary</button>
            </a>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def summarize():
    global latest_summary_text
    summary_text = None

    if request.method == "POST":
        try:
            response = requests.get(SPEECH_TO_TEXT_API)
            if response.status_code != 200:
                summary_text = f"Error fetching transcript: {response.text}"
            else:
                transcript = response.json().get("transcript", "").strip()
                if not transcript:
                    summary_text = "❌ No transcript found."
                else:
                    custom_prompt = request.form.get("custom_prompt", "").strip()
                    if custom_prompt:
                        prompt = f"{custom_prompt}\n\nTranscript:\n{transcript}"
                    else:
                        prompt = f"Summarize the following contents and give an in-depth explanation:\n\n{transcript}"

                    model = genai.GenerativeModel("gemini-1.5-pro-latest")
                    gemini_response = model.generate_content(prompt)
                    summary_text = gemini_response.text.strip()
                    latest_summary_text = summary_text

        except Exception as e:
            summary_text = f"Error generating summary: {str(e)}"

    return render_template_string(HTML_TEMPLATE, summary=summary_text)


@app.route("/latest_summary", methods=["GET"])
def get_latest_summary():
    if latest_summary_text:
        return jsonify({"summary": latest_summary_text})
    return jsonify({"error": "No summary available"}), 404


@app.route("/download_summary", methods=["GET"])
def download_summary():
    if latest_summary_text:
        file_stream = io.StringIO(latest_summary_text)
        return send_file(
            io.BytesIO(file_stream.getvalue().encode("utf-8")),
            as_attachment=True,
            download_name="summary.txt",
            mimetype="text/plain"
        )
    return jsonify({"error": "No summary available"}), 404


if __name__ == "__main__":
    app.run(port=5002, debug=True)
