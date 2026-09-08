#!/usr/bin/env python3
"""MBC 라디오 스트림 토큰 갱신.

MBC는 sminiplay.imbc.com 에서 서명 토큰(_lsu_sa_)이 붙은 재생 주소를 발급하는데,
이 엔드포인트가 Access-Control-Allow-Origin 헤더를 주지 않아 브라우저에서 직접
호출할 수 없다. 반면 스트림 서버(minisw/minimw/minicw.imbc.com)는 CORS를 허용한다.
그래서 이 스크립트가 GitHub Actions에서 대신 주소를 받아 radio/mbc.json 에 적어두고,
웹앱은 같은 출처의 그 파일만 읽는다. (토큰이 IP에 묶여 있지 않음을 실측으로 확인함.)

기존 토큰이 아직 살아 있으면 아무것도 쓰지 않는다 → 불필요한 커밋이 생기지 않는다.
"""

import datetime
import json
import pathlib
import urllib.request

CHANNELS = {"sfm": "표준FM", "mfm": "FM4U", "chm": "올댓뮤직"}
OUT = pathlib.Path("mbc.json")
ISSUER = "https://sminiplay.imbc.com/aacplay.ashx?channel={ch}&protocol=M3U8&agent=webapp"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; kr-fm-radio/1.0)"}


def fetch(url, timeout):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def alive(url):
    """저장돼 있는 재생 주소가 아직 유효한지 확인."""
    try:
        status, body = fetch(url, 10)
    except Exception:
        return False
    return status == 200 and body.lstrip().startswith("#EXTM3U")


def issue(ch):
    """새 재생 주소 발급."""
    status, body = fetch(ISSUER.format(ch=ch), 15)
    url = body.strip()
    if status != 200 or not url.startswith("https://") or ".m3u8" not in url:
        raise RuntimeError("예상치 못한 응답 (HTTP %s): %r" % (status, url[:100]))
    return url


def main():
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("channels", {})
        except Exception as e:
            print("기존 mbc.json 을 읽지 못해 새로 만듭니다: %s" % e)

    new, failed = {}, []
    for ch in CHANNELS:
        cur = old.get(ch)
        if cur and alive(cur):
            new[ch] = cur
            print("%-4s 기존 토큰 유효 — 유지" % ch)
            continue
        try:
            new[ch] = issue(ch)
            print("%-4s 새 토큰 발급" % ch)
        except Exception as e:
            if cur:
                new[ch] = cur          # 발급 실패 시 옛 주소라도 남겨 둔다
            failed.append("%s: %s" % (ch, e))
            print("%-4s 발급 실패 — %s" % (ch, e))

    missing = [ch for ch in CHANNELS if ch not in new]

    if new == old:
        print("모든 토큰이 아직 유효합니다 — 커밋할 변경 없음")
        return 1 if missing else 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": datetime.datetime.now(datetime.timezone.utc)
                           .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "names": CHANNELS,
        "channels": new,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("%s 갱신 완료 (채널 %d개)" % (OUT, len(new)))

    for f in failed:
        print("경고 — %s" % f)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
