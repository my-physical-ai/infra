#!/bin/bash
# make_team_nuc.sh - [방향A] 각 NUC에 team_id만 다르게 주입. 4070은 공유(포트 9200/8500 그대로).
# 사용법: 각 팀 NUC에서  bash make_team_nuc.sh 1   (그 NUC가 팀1이면)

set -e

TEAM="$1"
if [ -z "$TEAM" ]; then
  echo "사용법: bash make_team_nuc.sh [팀번호]"
  echo "  예: 이 NUC가 팀1이면  bash make_team_nuc.sh 1"
  exit 1
fi

SERVER_IP="192.168.0.36"          # 4070 IP (모든 팀 공유)
OS_PORT=9200                       # 공유 OpenSearch (방향A는 포트 안 나눔)
REC_PORT=$((8600 + TEAM))          # 녹화서버만 NUC별로 분리 (8601~8604)
STREAM="safety_team${TEAM}"        # 영상 스트림 이름 (팀별)
INDEX="safety-zone-events"         # ★공유 인덱스 (team_id로 구분)
DIR="team${TEAM}_nuc"
SRC="${SRC_NUC:-./_src_nuc}"      # 원본 NUC 폴더

echo "=== [방향A] 팀${TEAM} NUC 생성 ==="
echo "  team_id     : team${TEAM} (공유 인덱스에 구분 저장)"
echo "  영상 스트림 : ${STREAM}"
echo "  녹화 서버   : 포트 ${REC_PORT}"
echo "  데이터 전송 : ${SERVER_IP}:${OS_PORT} (공유 인덱스 ${INDEX})"

mkdir -p "${DIR}"

# ---------- intrusion_detector.py (team_id 주입, 4070은 공유) ----------
cp "${SRC}/intrusion_detector.py" "${DIR}/intrusion_detector.py"
# 영상 스트림만 팀별로 (4070 주소/인덱스는 그대로 공유)
sed -i "s|rtsp://127.0.0.1:8554/safety|rtsp://127.0.0.1:8554/${STREAM}|g" "${DIR}/intrusion_detector.py"
sed -i "s|ZONE_ID = \"zone-A\"|ZONE_ID = \"team${TEAM}-zone\"|g" "${DIR}/intrusion_detector.py"
# 침범 이벤트에 team_id 추가
sed -i "s|\"camera_id\": \"nuc-realsense\",|\"camera_id\": \"nuc-realsense\",\n        \"team_id\": \"team${TEAM}\",|g" "${DIR}/intrusion_detector.py"

# ---------- recording_server.py (녹화 포트만 분리) ----------
cp "${SRC}/recording_server.py" "${DIR}/recording_server.py"
sed -i "s|PORT = 8600|PORT = ${REC_PORT}|g" "${DIR}/recording_server.py"

# ---------- mediamtx.yml (스트림 경로 분리) ----------
cp "${SRC}/mediamtx.yml" "${DIR}/mediamtx.yml"
sed -i "s|  safety:|  ${STREAM}:|g" "${DIR}/mediamtx.yml"

# ---------- docker-compose.mediamtx.yml (컨테이너명 분리) ----------
cp "${SRC}/docker-compose.mediamtx.yml" "${DIR}/docker-compose.mediamtx.yml"
sed -i "s|container_name: safety-mediamtx|container_name: safety-mediamtx-team${TEAM}|g" "${DIR}/docker-compose.mediamtx.yml"

cp "${SRC}/requirements.txt" "${DIR}/requirements.txt"

echo ""
echo "✅ 생성 완료: ${DIR}/"
echo ""
echo "이 NUC에서 실행:"
echo "  cd ${DIR}"
echo "  sudo apt install -y ffmpeg && pip install -r requirements.txt"
echo "  docker compose -f docker-compose.mediamtx.yml up -d"
echo "  python3 intrusion_detector.py       # 터미널1"
echo "  python3 recording_server.py         # 터미널2 (녹화서버 ${REC_PORT})"
