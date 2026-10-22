#!/usr/bin/env python3
"""每天自动从 tweets.txt 读取一条文案并发布到 X(Twitter)。

- 文案按"一年中的第几天"轮换，保证每天内容不同、不重复太快。
- 凭据通过环境变量传入（见下方说明），不要写死在代码里。
"""
import os
import sys
from datetime import datetime

import tweepy

TWEETS_FILE = os.path.join(os.path.dirname(__file__), "tweets.txt")


def load_tweets(path: str) -> list[str]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到文案文件: {path}")
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        raise ValueError("tweets.txt 为空，请至少写一条文案")
    return lines


def pick_tweet(tweets: list[str]) -> str:
    # 用"年内的第几天"取模，均匀分布
    day_of_year = datetime.now().timetuple().tm_yday
    return tweets[day_of_year % len(tweets)]


def post_tweet(text: str) -> str:
    client = tweepy.Client(
        consumer_key=os.environ["API_KEY"],
        consumer_secret=os.environ["API_SECRET"],
        access_token=os.environ["ACCESS_TOKEN"],
        access_token_secret=os.environ["ACCESS_SECRET"],
    )
    resp = client.create_tweet(text=text)
    return resp.data["id"]


def main() -> int:
    required = ["API_KEY", "API_SECRET", "ACCESS_TOKEN", "ACCESS_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"缺少环境变量: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        tweets = load_tweets(TWEETS_FILE)
        text = pick_tweet(tweets)
        tweet_id = post_tweet(text)
        print(f"✅ 已发布推文 id={tweet_id}: {text}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ 发布失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
