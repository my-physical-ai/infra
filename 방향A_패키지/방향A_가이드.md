# 🏫 4팀 통합 관제 가이드 (방향 A — 공유 + team_id 구분)

4070 **한 세트**만 띄우고, 각 팀 NUC가 `team_id`를 붙여 전송 →
대시보드에서 팀을 골라보거나 전체 통합으로 한눈에 봅니다.

## 핵심 개념
```
NUC팀1 ─┐ team_id=team1
NUC팀2 ─┤ team_id=team2   → 4070 한 세트 (OpenSearch 1개)
NUC팀3 ─┤ team_id=team3      └ 같은 인덱스에 team_id로 구분 저장
NUC팀4 ─┘ team_id=team4      └ 대시보드 "팀 선택"으로 필터
```

실제 관제센터가 여러 구역을 한 화면에서 통합 관제하는 방식 = 더 현실적인 학습.

## 포트 (방향 B와 달리 4070은 1세트뿐)

| 항목 | 포트 | 비고 |
|------|------|------|
| OpenSearch | 9200 | **공유** (1개) |
| Dashboards | 5601 | **공유** (1개) |
| 관제 대시보드 | 8500 | **공유** (1개, 팀 선택으로 구분) |
| NUC 녹화서버 | 8601~8604 | 팀별 (충돌 방지) |
| 영상 스트림 | safety_team1~4 | 팀별 |

모두가 같은 대시보드 접속: **http://192.168.0.36:8500**
→ 우측 상단 "팀 선택" 드롭다운으로 팀1/팀2/.../전체 골라보기

## 생성 방법

### 4070에서 (공유 1세트)
```bash
cd 4070_공용
# 기존 안전지역 시스템과 동일하게 실행
docker compose -f docker-compose.opensearch.yml up -d
pip install -r requirements.txt
python3 create_index.py              # team_id 필드 포함 인덱스
cd dashboard && python3 control_server.py
```

### 각 팀 NUC에서 (자기 팀 번호로)
```bash
bash make_team_nuc.sh 1     # 팀1 NUC에서 → team1_nuc 생성
# 팀2 NUC: bash make_team_nuc.sh 2 ...
```
그다음 생성된 폴더에서:
```bash
cd team${팀번호}_nuc
sudo apt install -y ffmpeg && pip install -r requirements.txt
docker compose -f docker-compose.mediamtx.yml up -d
python3 intrusion_detector.py       # 터미널1
python3 recording_server.py         # 터미널2
```

## 대시보드 사용법 (팀 구분)

1. 모두 http://192.168.0.36:8500 접속
2. 우측 상단 드롭다운:
   - **🏢 전체 통합 보기**: 4팀 침범을 한눈에
   - **👷 team1 (N건)**: 팀1만 골라보기
3. 팀을 바꾸면 통계·실시간·검색이 그 팀 데이터로 갱신됩니다.

## 방향 A의 장점
- 4070 한 세트라 **메모리 부담 적음** (OpenSearch 1개)
- 강사가 **전체 통합 화면**으로 모든 팀 진행상황 한눈에 모니터링
- 팀끼리 서로의 데이터를 보며 비교·토론 가능
- 실제 관제센터 구조와 동일

## 데이터 확인 (팀별)
```bash
# 전체 개수
curl "http://192.168.0.36:9200/safety-zone-events/_count?pretty"

# 팀1만 개수
curl -X POST "http://192.168.0.36:9200/safety-zone-events/_search?pretty" \
  -H 'Content-Type: application/json' -d'
{ "size":0, "query":{"term":{"team_id":"team1"}} }'

# 팀별 침범 횟수 한 번에
curl -X POST "http://192.168.0.36:9200/safety-zone-events/_search?pretty" \
  -H 'Content-Type: application/json' -d'
{ "size":0, "aggs":{"by_team":{"terms":{"field":"team_id"}}} }'
```

## 주의
- NUC IP는 팀마다 다릅니다. 대시보드 "실시간 영상/녹화 보기"는 현재 단일 NUC(192.168.0.65) 기준입니다.
  팀별 영상까지 대시보드에서 보려면 NUC IP를 팀 선택과 연동하는 추가 작업이 필요합니다 (요청 시 구현).
- 핵심인 **침범 데이터 통합·검색·팀필터**는 완성되어 있습니다.
