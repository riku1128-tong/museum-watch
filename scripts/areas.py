"""観光地（泊まりがけで美術館をめぐる人が多い地域）の定義。中心の緯度・経度と半径で館を集める。

使い道:
    extras.build_areas   地域ごとの特集ページ（f/area-<key>.html）。宿のアフィリエイトの置き場所（area）もここ
    plan_run             まだ巡回していない館のうち、観光地の館を先に巡回する

museums.json の市区町村は Wikipedia の書き方しだいで欠けたり町名になったりするので、使わない。
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

# key, 表示名, 都道府県, 中心の緯度, 経度, 半径 km, 紹介文
AREAS = [
    ("hakone", "箱根", "神奈川県", 35.238, 139.055, 9, "温泉と美術館をいっしょに楽しめる、関東でいちばんの美術館の集まる地域。"),
    ("kamakura", "鎌倉・葉山", "神奈川県", 35.300, 139.560, 8, "古都の散策と海辺の美術館をあわせてめぐれる地域。"),
    ("ueno", "上野", "東京都", 35.716, 139.775, 1.2, "国立の美術館・博物館が上野公園に集まる、日本の美術館めぐりの中心地。"),
    ("karuizawa", "軽井沢", "長野県", 36.348, 138.597, 8, "避暑地の森の中に、個性的な美術館が点在する地域。"),
    ("azumino", "安曇野", "長野県", 36.305, 137.900, 10, "北アルプスのふもとに小さな美術館が点在する「美術館めぐり」の里。"),
    ("kanazawa", "金沢", "石川県", 36.561, 136.658, 6, "工芸と現代美術の街。兼六園の周りに美術館が集まる。"),
    ("kyoto", "京都", "京都府", 35.011, 135.768, 7, "岡崎・東山を中心に、日本美術の名品に出会える美術館が多い古都。"),
    ("nara", "奈良", "奈良県", 34.685, 135.840, 5, "仏教美術の宝庫。奈良公園の周りに美術館・博物館が集まる。"),
    ("kurashiki", "倉敷", "岡山県", 34.595, 133.772, 4, "白壁の美観地区に、日本初の西洋美術の私立美術館がある街。"),
    ("setouchi", "直島・豊島", "香川県", 34.470, 134.020, 12, "瀬戸内の島々に、建築と現代美術の美術館が点在する「アートの島」。"),
]


def km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def area_of(m: dict) -> str | None:
    """館が入っている観光地の key。どこにも入らなければ None（範囲が重なるときは最初の地域）。"""
    if m.get("lat") is None or m.get("lng") is None:
        return None
    for key, _, pref, lat, lng, r, _ in AREAS:
        if m["prefecture"] == pref and km(m["lat"], m["lng"], lat, lng) <= r:
            return key
    return None


def place_name(m: dict) -> str:
    """宿の検索などに使う地名。観光地の中なら地域名（例: 箱根）、そうでなければ市区町村、無ければ都道府県。"""
    key = area_of(m)
    if key:
        return next(name for k, name, *_ in AREAS if k == key)
    return m.get("municipality") or m["prefecture"]
