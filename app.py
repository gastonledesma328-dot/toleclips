import os
import uuid
import cv2
import mediapipe as mp
import subprocess
from flask import Flask, render_template, request, send_file
from faster_whisper import WhisperModel

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

model = WhisperModel("tiny")

mp_face = mp.solutions.face_detection.FaceDetection(
    model_selection=1,
    min_detection_confidence=0.5
)

def detect_face_region(video_path, output_face_path):
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    if not ret:
        cap.release()
        return None

    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb)

    if results.detections:
        bbox = results.detections[0].location_data.relative_bounding_box
        x = int(bbox.xmin * w)
        y = int(bbox.ymin * h)
        bw = int(bbox.width * w)
        bh = int(bbox.height * h)

        # Expandir área
        margin = 0.4
        x = max(0, int(x - bw * margin))
        y = max(0, int(y - bh * margin))
        bw = int(bw * (1 + margin))
        bh = int(bh * (1 + margin))

        face_crop = frame[y:y+bh, x:x+bw]
        cv2.imwrite(output_face_path, face_crop)

    cap.release()
    return output_face_path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process_video():
    file = request.files["video"]
    preset = request.form.get("preset")

    unique_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_FOLDER, unique_id + ".mp4")
    vertical_path = os.path.join(OUTPUT_FOLDER, unique_id + "_vertical.mp4")
    face_img_path = os.path.join(OUTPUT_FOLDER, unique_id + "_face.png")
    final_video = os.path.join(OUTPUT_FOLDER, unique_id + "_final.mp4")

    file.save(input_path)

    # 1️⃣ Crear base vertical
    subprocess.run([
        "ffmpeg","-y",
        "-i", input_path,
        "-vf", "crop=in_h*9/16:in_h,scale=1080:1920",
        "-c:a","copy",
        vertical_path
    ])

    # 2️⃣ Detectar cara
    detect_face_region(input_path, face_img_path)

    # 3️⃣ Definir posiciones preset
    positions = {
        "bottom_right": "W-w-20:H-h-20",
        "bottom_left": "20:H-h-20",
        "top_right": "W-w-20:20",
        "top_left": "20:20",
        "center": "(W-w)/2:(H-h)/2"
    }

    overlay_position = positions.get(preset, "W-w-20:H-h-20")

    # 4️⃣ Overlay facecam
    subprocess.run([
        "ffmpeg","-y",
        "-i", vertical_path,
        "-i", face_img_path,
        "-filter_complex",
        f"[1]scale=300:-1[face];[0][face]overlay={overlay_position}",
        "-c:a","copy",
        final_video
    ])

    return send_file(final_video, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
