# 🟩 이 폴더는 NUC (192.168.0.65) 에서 실행합니다

RealSense가 연결된 NUC에서 감지 + 영상 송출을 담당합니다.

## 이 폴더의 파일
| 파일 | 역할 |
|------|------|
| `intrusion_detector.py` | RealSense 감지 + 침범적재 + 영상송출 (메인) |
| `mediamtx.yml` | MediaMTX 설정 (RTSP 8554 → WebRTC 8889) |
| `docker-compose.mediamtx.yml` | MediaMTX 컨테이너 정의 |
| `requirements.txt` | Python 의존성 |

## 실행 순서
```bash
# 0) 이 폴더로 이동
cd 01_NUC_여기실행

# 1) 영상 송출용 ffmpeg 설치
sudo apt install -y ffmpeg

# 2) Python 의존성 설치
pip install -r requirements.txt

# 3) MediaMTX 영상중계 서버 실행 (파일명이 기본이 아니므로 -f 로 지정)
docker compose -f docker-compose.mediamtx.yml up -d

# 4) 감지기 실행 (감지 + 영상송출 동시)
python3 intrusion_detector.py
#   RealSense 없이 데모:  python3 intrusion_detector.py --simulate
#   영상 없이 감지만:     python3 intrusion_detector.py --no-stream
```

## ⚙️ 실행 전 확인할 값
- `mediamtx.yml` → `webrtcAdditionalHosts: [192.168.0.65]` 를 실제 NUC IP로
- `intrusion_detector.py` 상단 → `OPENSEARCH_URL = "http://192.168.0.36:9200"` (4070 주소, 맞으면 그대로)

## ⚠️ 순서 주의
- **4070이 먼저 떠 있어야** 침범 이벤트 적재가 됩니다.
- MediaMTX(3번)가 먼저 떠야 감지기(4번) 영상 push가 성공합니다.

## 🎬 침범 녹화 (신규)
- 침범이 감지되면 자동으로 녹화 시작 → 침범이 끝나면 mp4로 저장됩니다.
- 저장 위치: `~/safe_recordings/intrusion_YYYYMMDD_HHMMSS.mp4`
- 녹화 끄려면: `python3 intrusion_detector.py --no-record`

## ⚠️ 녹화 영상을 대시보드에서 보려면
4070 대시보드가 이 영상을 읽어야 합니다. 두 가지 방법:
1. (간단) NUC의 `~/safe_recordings`를 4070의 `~/safe_recordings`로 주기적 복사(rsync)
2. (권장) NFS/공유폴더로 두 머신이 같은 폴더를 바라보게 마운트
→ 4070 control_server.py의 `RECORDINGS_DIR` 경로와 일치시키면 됩니다.
