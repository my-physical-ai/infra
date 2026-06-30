# NUC에서 RealSense로 사람을 추적해 안전지역 침범을 4070 OpenSearch에 적재하고,
# 컬러 영상을 MediaMTX로 송출하며, 침범 발생 시 그 구간을 mp4로 녹화 저장하는 감지기.
# RealSense 미연결 시 --simulate 로 가상 데이터 생성 가능. --no-stream 으로 영상 송출 끌 수 있음.

import argparse
import datetime
import os
import random
import subprocess
import time

import requests

# ===== 사용자 환경 설정 (여기만 바꾸면 됨) =====
OPENSEARCH_URL = "http://192.168.0.36:9200"   # ← 4070 머신 OpenSearch 주소
INDEX_NAME = "safety-zone-events"
SAFE_DISTANCE_CM = 50.0                         # ← 안전 거리 임계값(cm)
ZONE_ID = "team1-zone"                              # ← 감시 구역 ID
YOLO_MODEL = "yolo26n.pt"                       # ← 모델 크기: n/s/m/l/x
CONF_THRESHOLD = 0.4                            # ← 사람 감지 신뢰도 하한
PERSON_CLASS = 0                                # COCO 'person' 클래스 번호

# 영상 송출 설정 (NUC 로컬 MediaMTX로 RTSP push)
RTSP_URL = "rtsp://127.0.0.1:8554/safety_team1"      # ← MediaMTX 스트림 경로 (대시보드 STREAM_NAME과 일치)
FRAME_W, FRAME_H, FPS = 640, 480, 15           # 송출 해상도/프레임레이트

# 침범 녹화 설정
RECORDINGS_DIR = os.path.expanduser("~/safe_recordings")  # ← 침범 영상 저장 폴더 (4070과 공유/동기화)
REC_TAIL_SECONDS = 2.0                          # 침범 종료 후 추가 녹화 시간(여운)
# ============================================


def now_iso() -> str:
    """현재 시각을 UTC ISO 문자열로 반환한다."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def send_event(worker_id: str, distance_cm: float, confidence: float) -> None:
    """침범 이벤트 한 건을 OpenSearch에 적재한다."""
    severity = "high" if distance_cm < 30 else "mid" if distance_cm < 50 else "low"
    doc = {
        "timestamp": now_iso(),
        "worker_id": worker_id,
        "event_type": "intrusion",
        "zone_id": ZONE_ID,
        "distance_cm": round(distance_cm, 1),
        "min_distance_cm": SAFE_DISTANCE_CM,
        "severity": severity,
        "camera_id": "nuc-realsense",
        "team_id": "team1",
        "confidence": round(confidence, 2),
        "message": f"작업자 {worker_id} 안전지역 {ZONE_ID} 침범 (거리 {distance_cm:.0f}cm)",
    }
    try:
        r = requests.post(f"{OPENSEARCH_URL}/{INDEX_NAME}/_doc", json=doc, timeout=3)
        print(f"[{r.status_code}] 침범 {worker_id} dist={distance_cm:.0f}cm conf={confidence:.2f}")
    except requests.RequestException as exc:
        print(f"[ERR] OpenSearch 적재 실패: {exc}")


def get_depth_at(depth_frame, cx: float, cy: float, half: int = 5) -> float:
    """깊이 프레임에서 (cx, cy) 주변 작은 영역의 중앙값 거리를 cm로 반환한다."""
    import numpy as np

    depth = np.asanyarray(depth_frame.get_data())   # mm 단위 z16 배열
    h, w = depth.shape
    x, y = int(cx), int(cy)
    x0, x1 = max(0, x - half), min(w, x + half)
    y0, y1 = max(0, y - half), min(h, y + half)
    patch = depth[y0:y1, x0:x1]
    valid = patch[patch > 0]                          # 0(무효 측정) 제외
    if valid.size == 0:
        return 9999.0
    return float(np.median(valid)) / 10.0             # mm -> cm


def open_rtsp_writer():
    """ffmpeg 프로세스를 열어 BGR 프레임을 RTSP(MediaMTX)로 push한다."""
    cmd = [
        "ffmpeg", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{FRAME_W}x{FRAME_H}", "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-f", "rtsp", "-rtsp_transport", "tcp", RTSP_URL,
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


class IntrusionRecorder:
    """침범이 시작되면 녹화를 시작하고, 침범이 끝나면 H.264 mp4로 저장하는 녹화기.

    OpenCV VideoWriter는 H.264 인코더를 환경에 따라 못 잡는 경우가 많으므로
    ffmpeg subprocess에 프레임을 직접 보내 libx264(소프트웨어)로 인코딩한다.
    이렇게 하면 하드웨어 인코더 없이도 브라우저 재생 가능한 H.264 mp4가 만들어진다.
    """

    def __init__(self):
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        self.proc = None        # ffmpeg subprocess
        self.filename = None
        self.last_intrusion_time = 0.0

    def _open_ffmpeg(self, filename: str):
        """raw BGR 프레임을 받아 H.264 mp4로 저장하는 ffmpeg 프로세스를 연다."""
        cmd = [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{FRAME_W}x{FRAME_H}", "-r", str(FPS),
            "-i", "-",
            "-c:v", "libx264", "-preset", "ultrafast",   # 소프트웨어 H.264 (하드웨어 불필요)
            "-pix_fmt", "yuv420p",                         # 브라우저 호환 픽셀 포맷
            "-movflags", "+faststart",                     # 웹 재생 최적화
            filename,
        ]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def update(self, frame, any_intrusion: bool) -> None:
        """매 프레임 호출. 침범 상태에 따라 녹화 시작/유지/종료를 관리한다.

        Args:
            frame: 저장할 BGR 프레임 (박스 오버레이된 것)
            any_intrusion: 이번 프레임에 침범자가 한 명이라도 있으면 True
        """
        now = time.time()

        if any_intrusion:
            self.last_intrusion_time = now
            if self.proc is None:   # 녹화 시작
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                self.filename = os.path.join(RECORDINGS_DIR, f"intrusion_{ts}.mp4")
                self.proc = self._open_ffmpeg(self.filename)
                print(f"[REC] 녹화 시작(H.264): {self.filename}")

        if self.proc is not None:
            try:
                self.proc.stdin.write(frame.tobytes())   # 프레임을 ffmpeg로 전달
            except BrokenPipeError:
                print("[REC][ERR] ffmpeg 파이프 끊김")
            # 침범이 끝나고 여운 시간이 지나면 저장 종료
            if not any_intrusion and (now - self.last_intrusion_time) > REC_TAIL_SECONDS:
                self.proc.stdin.close()
                self.proc.wait()                          # 파일 완전히 닫힐 때까지 대기
                print(f"[REC] 녹화 저장 완료: {self.filename}")
                self.proc = None
                self.filename = None

    def close(self) -> None:
        """프로그램 종료 시 열려 있는 녹화를 안전하게 닫는다."""
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait()
            print(f"[REC] 종료 시 녹화 저장: {self.filename}")
            self.proc = None


def run_realsense(stream: bool = True, record: bool = True) -> None:
    """RealSense로 사람을 추적하고 침범 감지 + 영상송출 + 침범녹화를 수행한다.

    Args:
        stream: True면 컬러 영상에 박스를 그려 MediaMTX로 송출한다.
        record: True면 침범 구간을 mp4로 녹화 저장한다.
    """
    import cv2
    import pyrealsense2 as rs
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(YOLO_MODEL)

    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.color, FRAME_W, FRAME_H, rs.format.bgr8, 30)
    cfg.enable_stream(rs.stream.depth, FRAME_W, FRAME_H, rs.format.z16, 30)
    pipeline.start(cfg)
    align = rs.align(rs.stream.color)

    writer = open_rtsp_writer() if stream else None
    recorder = IntrusionRecorder() if record else None
    if stream:
        print(f"영상 송출 시작: {RTSP_URL}")
    if record:
        print(f"침범 녹화 폴더: {RECORDINGS_DIR}")
    print(f"RealSense + {YOLO_MODEL} 시작. Ctrl+C로 종료.")

    last_logged: dict[int, float] = {}
    cooldown_s = 3.0

    try:
        while True:
            frames = align.process(pipeline.wait_for_frames())
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            if not color_frame or not depth_frame:
                continue

            color = np.asanyarray(color_frame.get_data())   # 프레임 한 번만 읽어 감지+송출+녹화 공용

            results = model.track(
                color, persist=True, tracker="botsort.yaml",
                classes=[PERSON_CLASS], conf=CONF_THRESHOLD, verbose=False,
            )

            boxes = results[0].boxes
            now = time.time()
            any_intrusion = False   # 이번 프레임에 침범자가 있는지

            if boxes is not None and boxes.id is not None:
                for box in boxes:
                    track_id = int(box.id)
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    dist_cm = get_depth_at(depth_frame, cx, cy)
                    intruded = dist_cm < SAFE_DISTANCE_CM
                    if intruded:
                        any_intrusion = True

                    # 영상에 박스/거리 오버레이 (송출/녹화 모두 이 프레임 사용)
                    col = (0, 0, 255) if intruded else (0, 200, 0)
                    cv2.rectangle(color, (int(x1), int(y1)), (int(x2), int(y2)), col, 2)
                    cv2.putText(color, f"W-{track_id} {dist_cm:.0f}cm",
                                (int(x1), int(y1) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)

                    if intruded and now - last_logged.get(track_id, 0) >= cooldown_s:
                        send_event(f"W-{track_id}", dist_cm, float(box.conf))
                        last_logged[track_id] = now

            # 침범 시각 자막 (녹화/송출 영상에 표시)
            cv2.putText(color, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        (10, FRAME_H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            if recorder is not None:   # 침범 구간 녹화 관리
                recorder.update(color, any_intrusion)

            if stream and writer:      # MediaMTX로 push
                try:
                    writer.stdin.write(color.tobytes())
                except BrokenPipeError:
                    print("[WARN] 영상 송출 파이프 끊김 - 재연결")
                    writer = open_rtsp_writer()
            time.sleep(0.01)
    finally:
        pipeline.stop()
        if writer:
            writer.stdin.close()
            writer.wait()
        if recorder:
            recorder.close()


def run_simulate() -> None:
    """RealSense 없이 가상 침범 데이터를 생성한다 (실습/데모용)."""
    print("시뮬레이션 모드. 가상 침범 이벤트 생성 중... Ctrl+C로 종료.")
    workers = [1, 2, 3, 4]
    while True:
        if random.random() < 0.4:
            dist = random.uniform(15, 49)
            send_event(f"W-{random.choice(workers)}", dist, confidence=random.uniform(0.7, 0.99))
        time.sleep(random.uniform(2, 5))


def main() -> None:
    """진입점. 실행 모드를 선택한다."""
    ap = argparse.ArgumentParser(description="NUC 안전지역 침범 감지기 (YOLO26 + 녹화)")
    ap.add_argument("--simulate", action="store_true", help="RealSense 없이 가상 데이터 생성")
    ap.add_argument("--no-stream", action="store_true", help="영상 송출 끄기")
    ap.add_argument("--no-record", action="store_true", help="침범 녹화 끄기")
    args = ap.parse_args()
    if args.simulate:
        run_simulate()
    else:
        run_realsense(stream=not args.no_stream, record=not args.no_record)


if __name__ == "__main__":
    main()
