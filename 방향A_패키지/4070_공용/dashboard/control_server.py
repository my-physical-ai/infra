#!/usr/bin/env python3
# control_server.py - 관제 대시보드 백엔드. OpenSearch 조회 + 정적 대시보드 서빙 + 녹화영상 목록 제공
# N분 전 검색 + 날짜/시간 구간 검색 + 침범 녹화영상 조회 API 포함

import datetime
import os

import requests
from flask import Flask, jsonify, request, send_from_directory

OPENSEARCH_URL = "http://192.168.0.36:9200"   # ← 4070 머신 IP
INDEX_NAME = "safety-zone-events"
# [방법 B] NUC 영상 서버 주소 - 대시보드가 NUC 영상을 직접 가져옴 (rsync 복사 불필요)
NUC_RECORDING_SERVER = "http://192.168.0.65:8600"   # ← NUC IP : 영상서버 포트

app = Flask(__name__, static_folder="static")


def search_opensearch(query: dict) -> dict:
    """OpenSearch에 검색 요청을 보내고 결과 dict를 반환한다. 실패 시 error 키를 담아 반환."""
    try:
        r = requests.post(f"{OPENSEARCH_URL}/{INDEX_NAME}/_search", json=query, timeout=5)
        return r.json()
    except requests.RequestException as exc:
        return {"error": str(exc)}


def _team_filter(team: str) -> list:
    """팀 필터 조건을 만든다. team이 'all'이거나 비어있으면 전체(필터 없음)."""
    if team and team != "all":
        return [{"term": {"team_id": team}}]
    return []


@app.route("/")
def index():
    return send_from_directory("static", "dashboard.html")


@app.route("/api/teams")
def teams():
    """저장된 팀 목록을 반환한다 (대시보드 팀 선택 드롭다운용)."""
    query = {
        "size": 0,
        "aggs": {"teams": {"terms": {"field": "team_id", "size": 20}}},
    }
    data = search_opensearch(query)
    if "error" in data:
        return jsonify([])
    buckets = data.get("aggregations", {}).get("teams", {}).get("buckets", [])
    return jsonify([{"team_id": b["key"], "count": b["doc_count"]} for b in buckets])


@app.route("/api/recent")
def recent():
    """최근 침범 이벤트 (대시보드 실시간 갱신용). ?team=team1 로 팀 필터 가능."""
    team = request.args.get("team", "all")
    query = {
        "size": 30,
        "sort": [{"timestamp": {"order": "desc"}}],
        "query": {
            "bool": {
                "must": [{"term": {"event_type": "intrusion"}}],
                "filter": _team_filter(team),
            }
        },
    }
    data = search_opensearch(query)
    if "error" in data:
        return jsonify({"error": data["error"], "events": []}), 502
    hits = data.get("hits", {}).get("hits", [])
    return jsonify([h["_source"] for h in hits])


def _aggregate_workers(data: dict) -> list:
    """검색 결과에서 작업자별 침범횟수/최근접거리 집계 리스트를 만든다."""
    buckets = data.get("aggregations", {}).get("by_worker", {}).get("buckets", [])
    return [{
        "worker_id": b["key"],
        "count": b["doc_count"],
        "closest_cm": round(b["min_dist"]["value"], 1) if b["min_dist"]["value"] is not None else None,
    } for b in buckets]


def _range_query(start_iso: str, end_iso: str, team: str = "all") -> dict:
    """주어진 시간 구간 + 팀의 침범 이벤트 검색 + 작업자 집계 쿼리를 만든다."""
    return {
        "size": 100,
        "sort": [{"timestamp": {"order": "asc"}}],
        "query": {
            "bool": {
                "must": [{"term": {"event_type": "intrusion"}}],
                "filter": [{"range": {"timestamp": {"gte": start_iso, "lte": end_iso}}}]
                          + _team_filter(team),
            }
        },
        "aggs": {
            "by_worker": {
                "terms": {"field": "worker_id", "size": 10},
                "aggs": {"min_dist": {"min": {"field": "distance_cm"}}},
            }
        },
    }


@app.route("/api/lookback")
def lookback():
    """N분 전(예: 20분) 시점 ±window분 구간의 침범자를 찾는다.
    /api/lookback?minutes=20&window=5"""
    minutes = int(request.args.get("minutes", 20))
    window = int(request.args.get("window", 5))
    team = request.args.get("team", "all")
    now = datetime.datetime.now(datetime.timezone.utc)
    center = now - datetime.timedelta(minutes=minutes)
    start = (center - datetime.timedelta(minutes=window)).isoformat()
    end = (center + datetime.timedelta(minutes=window)).isoformat()

    data = search_opensearch(_range_query(start, end, team))
    if "error" in data:
        return jsonify({"error": data["error"], "workers": [], "events": []}), 502
    events = [h["_source"] for h in data.get("hits", {}).get("hits", [])]
    return jsonify({
        "search_window": {"from": start, "to": end, "center_minutes_ago": minutes},
        "workers": _aggregate_workers(data),
        "events": events,
    })


@app.route("/api/search_range")
def search_range():
    """날짜/시간 구간을 직접 지정해 침범자를 검색한다.
    /api/search_range?from=2026-06-30T09:00&to=2026-06-30T10:00
    프론트엔드에서 받은 시각은 로컬 시간 → UTC 변환해서 조회."""
    from_str = request.args.get("from")
    to_str = request.args.get("to")
    team = request.args.get("team", "all")
    if not from_str or not to_str:
        return jsonify({"error": "from/to 파라미터가 필요합니다", "workers": [], "events": []}), 400

    # 브라우저 datetime-local 값(예: 2026-06-30T09:00)을 UTC로 변환
    try:
        # 로컬 시간으로 파싱 후 UTC로
        local_from = datetime.datetime.fromisoformat(from_str)
        local_to = datetime.datetime.fromisoformat(to_str)
        # 타임존 정보가 없으면 시스템 로컬 타임존으로 간주
        if local_from.tzinfo is None:
            local_from = local_from.astimezone()
        if local_to.tzinfo is None:
            local_to = local_to.astimezone()
        start = local_from.astimezone(datetime.timezone.utc).isoformat()
        end = local_to.astimezone(datetime.timezone.utc).isoformat()
    except ValueError as exc:
        return jsonify({"error": f"시간 형식 오류: {exc}", "workers": [], "events": []}), 400

    data = search_opensearch(_range_query(start, end, team))
    if "error" in data:
        return jsonify({"error": data["error"], "workers": [], "events": []}), 502
    events = [h["_source"] for h in data.get("hits", {}).get("hits", [])]
    return jsonify({
        "search_window": {"from": start, "to": end},
        "workers": _aggregate_workers(data),
        "events": events,
    })


@app.route("/api/stats")
def stats():
    """전체 통계 (심각도별/구역별 집계). ?team=team1 로 팀 필터 가능."""
    team = request.args.get("team", "all")
    query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [{"term": {"event_type": "intrusion"}}],
                "filter": _team_filter(team),
            }
        },
        "aggs": {
            "by_severity": {"terms": {"field": "severity"}},
            "by_zone": {"terms": {"field": "zone_id"}},
        },
    }
    data = search_opensearch(query)
    if "error" in data:
        return jsonify({"error": data["error"]}), 502
    return jsonify(data.get("aggregations", {}))


@app.route("/api/recordings")
def recordings():
    """[방법 B] NUC 영상 서버에서 녹화 목록을 받아 그대로 전달한다 (복사 불필요)."""
    try:
        r = requests.get(f"{NUC_RECORDING_SERVER}/recordings", timeout=3)
        return jsonify(r.json())
    except requests.RequestException:
        return jsonify([])


if __name__ == "__main__":
    # 0.0.0.0 → 라즈베리파이/NUC/다른 브라우저 모두 접속 가능
    app.run(host="0.0.0.0", port=8500, debug=True)
