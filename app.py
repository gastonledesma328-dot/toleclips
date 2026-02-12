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

if not ASSEMBLY_API_KEY:
    print("⚠️ WARNING: ASSEMBLY_API_KEY not set")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process_video():
    try:
        file = request.files["video"]
        if not file:
            return "No se subió archivo"

        unique_id = str(uuid.uuid4())

        input_path = f"{UPLOAD_FOLDER}/{unique_id}.mp4"
        vertical_path = f"{OUTPUT_FOLDER}/{unique_id}_vertical.mp4"
        audio_path = f"{OUTPUT_FOLDER}/{unique_id}.wav"
        srt_path = f"{OUTPUT_FOLDER}/{unique_id}.srt"
        final_path = f"{OUTPUT_FOLDER}/{unique_id}_final.mp4"

        file.save(input_path)

        print("🎬 Convirtiendo a vertical...")

        # 1️⃣ Convertir a vertical
        subprocess.run([
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "crop=in_h*9/16:in_h,scale=720:1280",
            "-preset", "ultrafast",
            vertical_path
        ], check=True)

        print("🔊 Extrayendo audio...")

        # 2️⃣ Extraer audio
        subprocess.run([
            "ffmpeg", "-y",
            "-i", vertical_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            audio_path
        ], check=True)

        headers = {
            "authorization": ASSEMBLY_API_KEY
        }

        print("⬆️ Subiendo audio a AssemblyAI...")

        # 3️⃣ Subir audio
        with open(audio_path, "rb") as f:
            upload_response = requests.post(
                "https://api.assemblyai.com/v2/upload",
                headers=headers,
                data=f
            )

        print("Upload status:", upload_response.status_code)
        print("Upload response:", upload_response.text)

        if upload_response.status_code != 200:
            return f"Error upload: {upload_response.text}"

        audio_url = upload_response.json().get("upload_url")

        if not audio_url:
            return f"Upload failed: {upload_response.text}"

        print("📝 Creando transcripción...")

        # 4️⃣ Crear transcripción
        transcript_response = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            json={"audio_url": audio_url},
            headers=headers
        )

        print("Transcript status:", transcript_response.status_code)
        print("Transcript response:", transcript_response.text)

        if transcript_response.status_code != 200:
            return f"Transcript error: {transcript_response.text}"

        transcript_id = transcript_response.json().get("id")

        if not transcript_id:
            return f"No transcript ID: {transcript_response.text}"

        print("⏳ Esperando resultado...")

        # 5️⃣ Polling
        timeout = 120  # máximo 2 minutos
        start_time = time.time()

        while True:
            polling = requests.get(
                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                headers=headers
            )

            polling_data = polling.json()
            status = polling_data.get("status")

            print("Estado:", status)

            if status == "completed":
                break

            if status == "error":
                return f"Transcription failed: {polling_data}"

            if time.time() - start_time > timeout:
                return "Timeout esperando transcripción"

            time.sleep(3)

        print("📥 Descargando SRT...")

        # 6️⃣ Obtener SRT
        srt_response = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{transcript_id}/srt",
            headers=headers
        )

        if srt_response.status_code != 200:
            return f"SRT error: {srt_response.text}"

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_response.text)

        print("🎞 Quemando subtítulos...")

        # 7️⃣ Quemar subtítulos
        subprocess.run([
            "ffmpeg", "-y",
            "-i", vertical_path,
            "-vf", f"subtitles={srt_path}:force_style='Fontsize=24'",
            "-preset", "ultrafast",
            final_path
        ], check=True)

        print("✅ Listo!")

        return redirect(url_for("result", video_id=unique_id))

    except Exception as e:
        print("🔥 ERROR:", str(e))
        return f"Error interno: {str(e)}"


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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
