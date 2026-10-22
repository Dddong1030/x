#!/usr/bin/env python3
"""用 Buffer 免费 API 自动把 X 渠道的待发队列补满（最多 10 条，免费版上限）。

原理：
  1. 读取 Buffer 账户下的 X(Twitter) 渠道
  2. 查询当前待发队列条数
  3. 不足 TARGET 条时，从 tweets.txt 按日期轮询取文案自动加入队列
这样配合 GitHub Actions 每天跑一次，就能长期"无人值守每天发推"，且完全免费、官方合规。

环境变量：
  BUFFER_ACCESS_TOKEN  Buffer 访问令牌（必填）
  QUEUE_TARGET         队列补到多少条（默认 10，免费版上限）
"""
import os
import sys
from datetime import datetime

import requests

API = "https://api.bufferapp.com/1"
TWEETS_FILE = os.path.join(os.path.dirname(__file__), "tweets.txt")
TWITTER_LIMIT = 280  # X 单条字数上限


def load_tweets(path: str) -> list[str]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到文案文件: {path}")
    tweets = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                tweets.append(s)
    if not tweets:
        raise ValueError("tweets.txt 为空，请至少写一条文案")
    return tweets


def get_profiles(token: str) -> list[dict]:
    r = requests.get(f"{API}/profiles.json", params={"access_token": token}, timeout=30)
    r.raise_for_status()
    return r.json()


def pick_x_profile(profiles: list[dict]) -> dict:
    for p in profiles:
        if p.get("service") in ("twitter", "x"):
            return p
    if profiles:
        return profiles[0]
    raise RuntimeError("账户下没有任何已连接的渠道，请先在 Buffer 连接 X")


def pending_count(token: str, profile_id: str) -> int:
    r = requests.get(
        f"{API}/profiles/{profile_id}/updates/pending.json",
        params={"access_token": token, "count": 100},
        timeout=30,
    )
    r.raise_for_status()
    return len(r.json().get("updates", []))


def add_to_queue(token: str, profile_id: str, text: str) -> bool:
    r = requests.post(
        f"{API}/updates/create.json",
        data={"access_token": token, "profile_ids[]": profile_id, "text": text},
        timeout=30,
    )
    if r.status_code == 200:
        return True
    print(f"  ⚠️ 加入失败 HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
    return False


def main() -> int:
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        print("缺少环境变量 BUFFER_ACCESS_TOKEN", file=sys.stderr)
        return 1

    target = int(os.environ.get("QUEUE_TARGET", "10"))
    target = min(target, 10)  # 免费版硬上限 10 条

    try:
        tweets = load_tweets(TWEETS_FILE)
        profiles = get_profiles(token)
        prof = pick_x_profile(profiles)
        pid = prof["id"]
        print(f"渠道: {prof.get('service')} / {prof.get('formatted_username')} (id={pid})")

        count = pending_count(token, pid)
        print(f"当前待发队列: {count} 条，目标: {target} 条")
        need = target - count
        if need <= 0:
            print("✅ 队列已满，无需补充")
            return 0

        day = datetime.now().timetuple().tm_yday
        added = 0
        for i in range(need):
            text = tweets[(day + added) % len(tweets)]
            if len(text) > TWITTER_LIMIT:
                print(f"  ⚠️ 跳过超长文案({len(text)}字): {text[:20]}...")
                continue
            if add_to_queue(token, pid, text):
                added += 1
                print(f"  + 已加入: {text}")
        print(f"✅ 本次补充 {added} 条，队列现约 {count + added} 条")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ 运行出错: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
