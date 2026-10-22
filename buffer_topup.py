#!/usr/bin/env python3
"""Buffer 免费版 + 官方 GraphQL API，自动把 X 渠道队列补满（最多 10 条）。

Buffer 新 API（2026-05 起）是纯 GraphQL：单端点 POST https://api.buffer.com，
请求体 {"query": "...", "variables": {...}}，认证用 Authorization: Bearer <key>。
key 在 Buffer 后台 Settings → API → Personal Keys 生成，需勾选 posting 权限。

工作流程：
  1. 查 account → 取 organization id
  2. 用 organization id 查 channels → 找 X(Twitter) 渠道 id
  3. 查该渠道 queuedPosts 数量
  4. 不足 TARGET 条时，从 tweets.txt 按日期轮询，用 createPost(mode: addToQueue) 补满

环境变量：
  BUFFER_ACCESS_TOKEN  Buffer Personal Key（必填）
  QUEUE_TARGET         队列补到多少条（默认 10，免费版上限）
"""
import os
import sys
from datetime import datetime

import requests

API = "https://api.buffer.com"
TWITTER_LIMIT = 280
TWEETS_FILE = os.path.join(os.path.dirname(__file__), "tweets.txt")


def gql(token, query, variables=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"query": query}
    if variables is not None:
        body["variables"] = variables
    r = requests.post(API, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL 错误: {payload['errors']}")
    return payload.get("data", {})


def load_tweets(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到文案文件: {path}")
    tweets = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                tweets.append(s)
    if not tweets:
        raise ValueError("tweets.txt 为空")
    return tweets


def get_x_channel(token):
    org = gql(token, "query { account { organizations { id name } } }")
    orgs = org.get("account", {}).get("organizations", [])
    if not orgs:
        raise RuntimeError("账户下没有 organization，请先在 Buffer 连接 X 账号")
    org_id = orgs[0]["id"]
    q = 'query { channels(input: { organizationId: "%s" }) { id name service } }' % org_id
    d = gql(token, q)
    channels = d.get("channels", [])
    for c in channels:
        if c.get("service") in ("twitter", "x"):
            return c
    if channels:
        return channels[0]
    raise RuntimeError("Buffer 里没有连接任何渠道，请先连接 X")


def pending_count(token, channel_id):
    q = 'query { channel(id: "%s") { queuedPosts { edges { node { id } } } } }' % channel_id
    d = gql(token, q)
    return len(d.get("channel", {}).get("queuedPosts", {}).get("edges", []))


def add_to_queue(token, channel_id, text):
    q = """mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text } }
        ... on MutationError { message }
      }
    }"""
    variables = {
        "input": {
            "text": text,
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": "addToQueue",
        }
    }
    d = gql(token, q, variables)
    res = d.get("createPost", {})
    if "post" in res:
        return True
    print(f"  ⚠️ 加入失败: {res.get('message')}", file=sys.stderr)
    return False


def main():
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        print("缺少环境变量 BUFFER_ACCESS_TOKEN", file=sys.stderr)
        return 1
    target = min(int(os.environ.get("QUEUE_TARGET", "10")), 10)
    try:
        tweets = load_tweets(TWEETS_FILE)
        ch = get_x_channel(token)
        cid = ch["id"]
        print(f"渠道: {ch.get('service')} / {ch.get('name')} (id={cid})")
        count = pending_count(token, cid)
        print(f"当前队列: {count} 条，目标: {target} 条")
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
            if add_to_queue(token, cid, text):
                added += 1
                print(f"  + 已加入: {text}")
        print(f"✅ 本次补充 {added} 条，队列现约 {count + added} 条")
        return 0
    except Exception as e:
        print(f"❌ 运行出错: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
