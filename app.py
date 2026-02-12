import os
import uuid
import time
import requests
import subprocess
from flask import Flask, render_template, request, redirect, url_for, send_from_directory

app = Flask(__name__)

UPLOAD_FOLDER = "/tmp/uploads"
OUTPUT_FOLDER = "/tmp/outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ASSEMBLY_API_KEY = os.environ.get("ASSEMBLY_API_KEY")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process_video():
    file = request.files["video"]
    unique_id = str(uuid.uuid4())

    input_path = f"{UPLOAD_FOLDER}/{unique_id}.mp4"
    vertical_path = f"{OUTPUT_FOLDER}/{unique_id}_vertical.mp4"
    audio_path = f"{OUTPUT_FOLDER}/{unique_id}.wav"
    srt_path = f"{OUTPUT_FOLDER}/{unique_id}.srt"
    final_path = f"{OUTPUT_FOLDER}/{unique_id}_final.mp4"

    file.save(input_path)

    # 1️⃣ Convertir a vertical
    subprocess.run([
        "ffmpeg","-y",
        "-i", input_path,
        "-vf","crop=in_h*9/16:in_h,scale=720:1280",
        "-preset","ultrafast",
        vertical_path
    ])

    # 2️⃣ Extraer audio
    subprocess.run([
        "ffmpeg","-y",
        "-i", vertical_path,
        "-vn",
        "-ac","1",
        "-ar","16000",
        audio_path
    ])

    # 3️⃣ Subir audio a AssemblyAI
    headers = {
        "authorization": ASSEMBLY_API_KEY
    }

    upload_response = requests.post(
        "https://api.assemblyai.com/v2/upload",
        headers=headers,
        data=open(audio_path, "rb")
    )

    audio_url = upload_response.json()["upload_url"]

   transcript_response = requests.post(
    "https://api.assemblyai.com/v2/transcript",
    json={"audio_url": audio_url},
    headers=headers
)

transcript_data = transcript_response.json()

if "id" not in transcript_data:
    print("ERROR TRANSCRIPT:", transcript_data)
    return f"Error AssemblyAI: {transcript_data}"

transcript_id = transcript_data["id"]


    # 4️⃣ Esperar resultado
    while True:
        polling = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
            headers=headers
        )
        status = polling.json()["status"]

        if status == "completed":
            break
        elif status == "error":
            return "Error en transcripción"

        time.sleep(3)

    # 5️⃣ Obtener subtítulos en SRT
    srt_response = requests.get(
        f"https://api.assemblyai.com/v2/transcript/{transcript_id}/srt",
        headers=headers
    )

    with open(srt_path,"w",encoding="utf-8") as f:
        f.write(srt_response.text)

    # 6️⃣ Quemar subtítulos
    subprocess.run([
        "ffmpeg","-y",
        "-i", vertical_path,
        "-vf",f"subtitles={srt_path}:force_style='Fontsize=24'",
        "-preset","ultrafast",
        final_path
    ])

    return redirect(url_for("result", video_id=unique_id))


@app.route("/result/<video_id>")
def result(video_id):
    return render_template("result.html", video_id=video_id)


@app.route("/download/<video_id>")
def download(video_id):
    return send_from_directory(
        OUTPUT_FOLDER,
        f"{video_id}_final.mp4",
        as_attachment=True
    )


@app.route("/video/<video_id>")
def serve_video(video_id):
    return send_from_directory(
        OUTPUT_FOLDER,
        f"{video_id}_final.mp4"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
