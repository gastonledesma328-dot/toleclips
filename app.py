import os
import uuid
import subprocess
from flask import Flask, render_template, request, send_file
from faster_whisper import WhisperModel

app = Flask(__name__)

UPLOAD_FOLDER = "/tmp/uploads"
OUTPUT_FOLDER = "/tmp/outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Modelo optimizado para Render Free
model = WhisperModel(
    "tiny",
    compute_type="int8"
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process_video():
    file = request.files["video"]
    preset = request.form.get("preset")

    unique_id = str(uuid.uuid4())

    input_path = f"{UPLOAD_FOLDER}/{unique_id}.mp4"
    vertical_path = f"{OUTPUT_FOLDER}/{unique_id}_vertical.mp4"
    audio_path = f"{OUTPUT_FOLDER}/{unique_id}.wav"
    srt_path = f"{OUTPUT_FOLDER}/{unique_id}.srt"
    final_path = f"{OUTPUT_FOLDER}/{unique_id}_final.mp4"

    file.save(input_path)

    # 1️⃣ Convertir a vertical 9:16
    subprocess.run([
        "ffmpeg","-y",
        "-i", input_path,
        "-vf","crop=in_h*9/16:in_h,scale=720:1280",
        "-preset","ultrafast",
        vertical_path
    ])

    # 2️⃣ Extraer audio liviano
    subprocess.run([
        "ffmpeg","-y",
        "-i", vertical_path,
        "-vn",
        "-ac","1",
        "-ar","16000",
        audio_path
    ])

    # 3️⃣ Generar subtítulos
    segments, _ = model.transcribe(audio_path)

    with open(srt_path,"w",encoding="utf-8") as f:
        for i, seg in enumerate(segments,1):
            f.write(f"{i}\n")
            f.write(f"{format_time(seg.start)} --> {format_time(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")

    # 4️⃣ Quemar subtítulos al video vertical
    subprocess.run([
        "ffmpeg","-y",
        "-i", vertical_path,
        "-vf",f"subtitles={srt_path}:force_style='Fontsize=24'",
        "-preset","ultrafast",
        final_path
    ])

    return send_file(final_path, as_attachment=True)


def format_time(seconds):
    hrs = int(seconds//3600)
    mins = int((seconds%3600)//60)
    secs = int(seconds%60)
    ms = int((seconds-int(seconds))*1000)
    return f"{hrs:02}:{mins:02}:{secs:02},{ms:03}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
