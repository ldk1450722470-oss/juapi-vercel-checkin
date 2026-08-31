# -*- coding: utf-8 -*-
"""
JuAPI 自动签到 - Vercel Serverless 版本
账号密码通过环境变量配置，在 Vercel Dashboard -> Settings -> Environment Variables 里设置：

  JUAPI_LOGIN    : 账号（用户名或邮箱）
  JUAPI_PASSWORD : 密码
"""

import json
import os
import urllib.request
import urllib.error
from http.cookiejar import CookieJar
from flask import Flask, Response

app = Flask(__name__)

BASE_URL = "https://www.juapi.net"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 JuApi-Auto-Checkin"
)


def request_json(method, url, data=None, headers=None, cookie="", quiet=False):
    """发送 HTTP 请求并返回 JSON 结果。"""
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    if cookie:
        req.add_header("Cookie", cookie)
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    body = json.dumps(data).encode("utf-8") if data is not None else None
    try:
        with urllib.request.urlopen(req, data=body, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        if not quiet:
            print(f"[请求失败] {e}")
        return None


def format_num(v):
    return f"{v:,}" if v is not None else "未知"


def get_month():
    from time import strftime
    return strftime("%Y-%m")


def checkin_one(login, password):
    """对一个账号执行签到，返回日志文本列表。"""
    log = []
    def add(msg): log.append(msg)

    add(f"\n===== 账号：{login} =====")

    # 1. 登录
    add("  [登录] 正在登录...")
    login_res = request_json("POST", f"{BASE_URL}/api/user/login",
                             data={"username": login, "password": password})
    if not login_res or not login_res.get("success"):
        add(f"  [失败] 登录失败：{login_res.get('message', '未知')}")
        return log

    user = login_res["data"]
    user_id = user["id"]
    display = user.get("display_name") or user.get("username")
    add(f"  [成功] 登录成功，欢迎 {display}！")

    auth_headers = {"New-Api-User": str(user_id)}

    # 2. 查余额
    self_res = request_json("GET", f"{BASE_URL}/api/user/self",
                            headers=auth_headers)
    old_quota = self_res["data"].get("quota") if self_res and self_res.get("success") else None
    add(f"  [余额] 签到前余额：{format_num(old_quota)}")

    # 3. 查签到状态
    month = get_month()
    status_res = request_json("GET", f"{BASE_URL}/api/user/checkin?month={month}",
                              headers=auth_headers)
    if not status_res or not status_res.get("success"):
        add(f"  [失败] 获取签到状态失败：{status_res.get('message', '未知')}")
        return log

    stats = status_res["data"]["stats"]
    total = stats.get("total_checkins", 0)
    total_quota = stats.get("total_quota", 0)
    add(f"  [状态] 累计签到 {total} 天，累计获得额度 {format_num(total_quota)}")

    if stats.get("checked_in_today"):
        add("  [跳过] 今日已签到，无需重复")
        add(f"  [余额] 当前余额：{format_num(old_quota)}")
        return log

    # 4. 签到
    checkin_res = request_json("POST", f"{BASE_URL}/api/user/checkin",
                               data={}, headers=auth_headers)
    if checkin_res and checkin_res.get("success"):
        awarded = checkin_res["data"].get("quota_awarded")
        add(f"  [成功] 签到成功！本次获得额度：{format_num(awarded)}")

        new_res = request_json("GET", f"{BASE_URL}/api/user/self",
                               headers=auth_headers)
        new_quota = new_res["data"].get("quota") if new_res and new_res.get("success") else None
        add(f"  [余额] 签到后余额：{format_num(new_quota)}")
    else:
        add(f"  [失败] 签到失败：{checkin_res.get('message', '未知')}")

    return log


@app.route("/")
def checkin():
    """Vercel Cron 触发入口"""
    login = os.environ.get("JUAPI_LOGIN")
    password = os.environ.get("JUAPI_PASSWORD")

    if not login or not password:
        return Response("错误：未配置 JUAPI_LOGIN 和 JUAPI_PASSWORD 环境变量", status=500)

    logs = ["JuAPI 自动签到开始（Vercel）"]
    try:
        logs += checkin_one(login, password)
        logs.append("\n===== 签到完成 =====")
    except Exception as e:
        logs.append(f"\n[异常] {e}")

    return Response("\n".join(logs), mimetype="text/plain; charset=utf-8")
