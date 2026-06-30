# NUC에서 침범 녹화 영상(mp4)을 HTTP로 제공하는 작은 서버.
# 4070 대시보드가 이 서버에서 영상 목록과 파일을 직접 가져간다 (rsync 복사 불필요).

import datetime
import os

from flask import Flask, jsonify, send_from_directory

# 침범 녹화 영상이 저장된 폴더 (intrusion_detector.py의 RECORDINGS_DIR과 동일해야 함)
RECORDINGS_DIR = os.path.expanduser("~/safe_recordings")
PORT = 8600   # 영상 제공 포트 (대시보드가 이 포트로 요청)

app = Flask(__name__)


@app.after_request
def add_cors(resp):
    """4070 대시보드(다른 출처)에서 접근할 수 있도록 CORS 허용."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/recordings")
def list_recordings():
    """녹화 영상 파일 목록을 최신순으로 반환한다."""
    if not os.path.isdir(RECORDINGS_DIR):
        return jsonify([])
    files = []
    for name in os.listdir(RECORDINGS_DIR):
        if name.endswith((".mp4", ".avi")):
            path = os.path.join(RECORDINGS_DIR, name)
            files.append({
                "name": name,
                "size_kb": round(os.path.getsize(path) / 1024, 1),
                "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
            })
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return jsonify(files)


@app.route("/recordings/<path:filename>")
def get_recording(filename):
    """녹화 영상 파일 하나를 그대로 전송한다 (브라우저에서 재생)."""
    return send_from_directory(RECORDINGS_DIR, filename)


if __name__ == "__main__":
    print(f"녹화 영상 서버 시작: http://0.0.0.0:{PORT}  (폴더: {RECORDINGS_DIR})")
    app.run(host="0.0.0.0", port=PORT)
