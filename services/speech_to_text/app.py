from flask import Flask, request, jsonify, render_template
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import storage
from werkzeug.utils import secure_filename
import os
import uuid
import threading
import subprocess
import json

app = Flask(__name__)
app.config["UPLOAD_EXTENSIONS"] = [".mp3", ".wav", ".flac", ".ogg", ".opus", ".webm"]
app.config["UPLOAD_FOLDER"] = "temp"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(os.path.dirname(__file__), "gcloud.json")
GCS_BUCKET_NAME = "auto-quiz"
jobs = {}

def convert_webm_to_wav(input_path, output_path):
    try:
        subprocess.run(["ffmpeg", "-y", "-i", input_path, output_path], check=True)
        print(f"[CONVERT] Converted {input_path} -> {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Conversion failed: {e}")
        return False

def get_audio_encoding(filename):
    ext = filename.lower().split('.')[-1]
    return {
        "mp3": speech.RecognitionConfig.AudioEncoding.MP3,
        "wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
        "flac": speech.RecognitionConfig.AudioEncoding.FLAC,
        "ogg": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
        "opus": speech.RecognitionConfig.AudioEncoding.OGG_OPUS
    }.get(ext, speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED)

def upload_to_gcs(file_path, blob_name):
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(file_path)
    print(f"[UPLOAD] Uploaded to GCS: {blob_name}")
    return f"gs://{GCS_BUCKET_NAME}/{blob_name}"

def delete_from_gcs(blob_name):
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        blob.delete()
        print(f"[CLEANUP] Deleted from GCS: {blob_name}")
    except Exception as e:
        print(f"[CLEANUP WARN] Could not delete {blob_name}: {e}")

def transcribe_async(job_id, audio_path, blob_name, encoding):
    try:
        gcs_uri = upload_to_gcs(audio_path, blob_name)
        client = speech.SpeechClient()

        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="video",
            use_enhanced=True,
        )

        print(f"[TRANSCRIBE] Started job: {job_id}")
        operation = client.long_running_recognize(config=config, audio=audio)
        response = operation.result(timeout=900)

        transcript = " ".join([r.alternatives[0].transcript for r in response.results])
        jobs[job_id] = {"status": "done", "transcript": transcript}

       
        with open("latest_transcript.json", "w", encoding="utf-8") as f:
            json.dump({"transcript": transcript}, f)

        print(f"[TRANSCRIBE] Completed job: {job_id}")
    except Exception as e:
        jobs[job_id] = {"status": "error", "error": str(e)}
        print(f"[ERROR] {job_id} failed: {e}")
    finally:
        delete_from_gcs(blob_name)
        if os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"[CLEANUP] Deleted local: {audio_path}")

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in app.config["UPLOAD_EXTENSIONS"]:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    original_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}{ext}")
    file.save(original_path)

    final_path = original_path
    encoding = get_audio_encoding(original_path)

    if ext == ".webm":
        wav_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}.wav")
        if not convert_webm_to_wav(original_path, wav_path):
            return jsonify({"error": "Failed to convert audio"}), 500
        os.remove(original_path)
        final_path = wav_path
        encoding = speech.RecognitionConfig.AudioEncoding.LINEAR16
        ext = ".wav"

    blob_name = f"{job_id}{ext}"
    jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=transcribe_async,
        args=(job_id, final_path, blob_name, encoding),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id})

@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Invalid job ID"}), 404
    return jsonify(jobs[job_id])

@app.route("/latest_transcript", methods=["GET"])
def latest_transcript():
    try:
        with open("latest_transcript.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
