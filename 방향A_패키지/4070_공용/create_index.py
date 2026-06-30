#!/usr/bin/env python3
# create_index.py - 안전지역 침범 이벤트를 저장할 OpenSearch 인덱스와 매핑 생성

import requests
import json

OPENSEARCH_URL = "http://192.168.0.36:9200"   # ← 4070 머신 IP
INDEX_NAME = "safety-zone-events"

# 인덱스 매핑: 침범 이벤트 한 건의 구조 정의
mapping = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0    # 단일 노드라 복제본 0
    },
    "mappings": {
        "properties": {
            "timestamp":    {"type": "date"},          # 이벤트 발생 시각 (검색 핵심 필드)
            "worker_id":    {"type": "keyword"},
            "team_id":      {"type": "keyword"},        # ★팀 구분 (team1~team4)
            "event_type":   {"type": "keyword"},        # intrusion / warning / clear
            "zone_id":      {"type": "keyword"},        # 안전지역 구역 ID
            "distance_cm":  {"type": "float"},          # RealSense 측정 거리(cm)
            "min_distance_cm": {"type": "float"},       # 설정된 안전 거리 임계값
            "severity":     {"type": "keyword"},        # low / mid / high
            "camera_id":    {"type": "keyword"},        # 감지 카메라 (nuc-realsense)
            "confidence":   {"type": "float"},          # 감지 신뢰도
            "message":      {"type": "text"}            # 전문 검색용 설명 텍스트
        }
    }
}

def main():
    url = f"{OPENSEARCH_URL}/{INDEX_NAME}"
    # 기존 인덱스 있으면 삭제 (실습 반복용)
    requests.delete(url)
    r = requests.put(url, json=mapping)
    print(f"[{r.status_code}] 인덱스 생성: {INDEX_NAME}")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
