#!/bin/bash
# opensearch_check.sh - OpenSearch에 저장된 안전지역 침범 데이터를 단계별로 확인/검색하는 실습 스크립트
# 사용법: bash opensearch_check.sh [번호]   (번호 없으면 메뉴 표시)

# ===== 설정 (여기만 바꾸면 됨) =====
OS="http://192.168.0.36:9200"        # ← 4070 OpenSearch 주소
INDEX="safety-zone-events"           # 침범 이벤트 인덱스 이름
# ==================================

menu() {
  echo "==================================================="
  echo "  OpenSearch 데이터 확인/검색 실습"
  echo "==================================================="
  echo "  1) 연결 확인        - 서버가 살아있나?"
  echo "  2) 인덱스 목록      - 어떤 데이터 칸이 있나?"
  echo "  3) 데이터 개수      - 침범이 총 몇 건 쌓였나?"
  echo "  4) 최근 5건 보기    - 실제 내용 들여다보기"
  echo "  5) 작업자별 집계    - 누가 몇 번 침범했나?"
  echo "  6) 고위험만 검색    - 30cm 이내 침범만"
  echo "  7) 키워드 검색      - message에서 단어 찾기"
  echo "  8) 시간범위 검색    - 최근 1시간 침범"
  echo "==================================================="
  echo "사용법: bash opensearch_check.sh 3   (3번 실행)"
}

# 1) 연결 확인
check_connection() {
  echo "[1] OpenSearch 연결 확인..."
  curl -s "$OS" | head -20
}

# 2) 인덱스 목록
list_indices() {
  echo "[2] 인덱스(데이터 칸) 목록..."
  curl -s "$OS/_cat/indices?v"
}

# 3) 데이터 개수
count_docs() {
  echo "[3] 저장된 침범 이벤트 개수..."
  curl -s "$OS/$INDEX/_count?pretty"
}

# 4) 최근 5건 보기
show_recent() {
  echo "[4] 최근 침범 5건 (시각 내림차순)..."
  curl -s "$OS/$INDEX/_search?size=5&sort=timestamp:desc&pretty"
}

# 5) 작업자별 집계
aggregate_workers() {
  echo "[5] 작업자별 침범 횟수 + 최근접 거리 집계..."
  curl -s -X POST "$OS/$INDEX/_search?pretty" -H 'Content-Type: application/json' -d'
  {
    "size": 0,
    "aggs": {
      "by_worker": {
        "terms": { "field": "worker_id" },
        "aggs": { "closest_cm": { "min": { "field": "distance_cm" } } }
      }
    }
  }'
}

# 6) 고위험만 검색 (30cm 이내)
search_high_risk() {
  echo "[6] 고위험 침범 검색 (거리 30cm 미만)..."
  curl -s -X POST "$OS/$INDEX/_search?pretty" -H 'Content-Type: application/json' -d'
  {
    "size": 10,
    "sort": [{ "distance_cm": { "order": "asc" } }],
    "query": { "range": { "distance_cm": { "lt": 30 } } }
  }'
}

# 7) 키워드 검색
search_keyword() {
  echo "[7] message에서 '침범' 키워드 검색..."
  curl -s "$OS/$INDEX/_search?q=message:침범&size=3&pretty"
}

# 8) 시간범위 검색 (최근 1시간)
search_time_range() {
  echo "[8] 최근 1시간 침범 검색..."
  curl -s -X POST "$OS/$INDEX/_search?pretty" -H 'Content-Type: application/json' -d'
  {
    "size": 20,
    "sort": [{ "timestamp": { "order": "desc" } }],
    "query": { "range": { "timestamp": { "gte": "now-1h" } } }
  }'
}

case "$1" in
  1) check_connection ;;
  2) list_indices ;;
  3) count_docs ;;
  4) show_recent ;;
  5) aggregate_workers ;;
  6) search_high_risk ;;
  7) search_keyword ;;
  8) search_time_range ;;
  *) menu ;;
esac
