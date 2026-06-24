#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描各主题 SVG 目录，按主题关键词分类，每主题生成 icons-<theme>.json，
并产出 themes.json 清单，供 index.html 懒加载与多主题切换使用。

所有主题 SVG 目录与生成的 JSON 都收纳在项目根下的 Themes/ 子目录里，
保持项目根整洁；JSON 内记录的 SVG 路径**相对 Themes/**（不带 Themes/ 前缀），
前端 fetch 与 /api/pick 时再显式拼上 Themes/。
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(ROOT_DIR, "Themes")
MANIFEST_PATH = os.path.join(THEMES_DIR, "_iconify-manifest.json")
CAT_CACHE_DIR = os.path.join(THEMES_DIR, "_iconify-categories")

# 主题配置：每项描述一个图标主题如何被解析。
#   dir              — 子目录名
#   name             — 显示用主题名
#   file             — 输出 JSON 文件名
#   default          — 是否默认主题（前端首次加载它）
#   variants         — [(key, 中文标签, 结尾后缀正则)]；顺序重要：长后缀必须在前，
#                      否则 -rounded.svg 会先吃掉 -outline-rounded.svg，
#                      -bold.svg 会先吃掉 -bold-duotone.svg
#   fallback_variant — 命中不了任何后缀时（如裸 foo.svg）归到这里
#   categories       — None = 复用下面的 CATEGORIES；否则给一份该主题专属关键词
THEMES = [
    {
        "dir": "Material Symbols", "name": "Material Symbols",
        "file": "icons-material.json", "default": True,
        "variants": [
            ("outline", "描边", r"-outline-rounded\.svg$"),
            ("filled",  "填充", r"-rounded\.svg$"),
        ],
        "fallback_variant": "filled",
        "categories": None,
    },
    {
        "dir": "Lucide", "name": "Lucide", "file": "icons-lucide.json",
        "variants": [("default", "默认", r"\.svg$")],
        "fallback_variant": "default",
        "categories": None,
    },
    {
        "dir": "Solar", "name": "Solar", "file": "icons-solar.json",
        "variants": [
            ("bold-duotone", "粗体双色", r"-bold-duotone\.svg$"),
            ("line-duotone", "线性双色", r"-line-duotone\.svg$"),
            ("bold",    "粗体", r"-bold\.svg$"),
            ("broken",  "破碎", r"-broken\.svg$"),
            ("linear",  "线性", r"-linear\.svg$"),
            ("outline", "描边", r"-outline\.svg$"),
        ],
        "fallback_variant": "linear",
        "categories": None,
    },
    {
        "dir": "Tabler Icons", "name": "Tabler Icons", "file": "icons-tabler.json",
        "variants": [("default", "默认", r"\.svg$")],
        "fallback_variant": "default",
        "categories": None,
    },
    {
        "dir": "Carbon", "name": "Carbon", "file": "icons-carbon.json",
        "variants": [("default", "默认", r"\.svg$")],
        "fallback_variant": "default",
        "categories": None,
    },
    {
        # Fluent UI 命名：<icon>-<size>-<style>.svg（size∈16/20/24/28/48，style∈filled/regular）
        # 用两条后缀正则剥离 "-NN-filled/.svg" 与 "-NN-regular/.svg"，把同一图标的多个尺寸
        # 合并成一个图标名，filled/regular 作为两个形态。
        "dir": "Fluent UI System Icons", "name": "Fluent UI System Icons",
        "file": "icons-fluent.json",
        "variants": [
            ("filled",  "填充", r"-\d+-filled\.svg$"),
            ("regular", "线性", r"-\d+-regular\.svg$"),
        ],
        "fallback_variant": "regular",
        "categories": None,
    },
    {
        # Phosphor 6 种粗细：thin/light/regular/bold/fill/duotone。
        # 必须显式登记：贪婪检测会把 dot-outline-duotone / ghost-fill / sharp-bold
        # 这类"图标名恰好含风格词"的文件误判成复合形态（之前误生成 36 个）。
        # regular 是无后缀的兜底形态，用 \.svg$ 在最后兜住。
        "dir": "Phosphor", "name": "Phosphor", "file": "icons-phosphor.json",
        "variants": [
            ("thin",    "特细", r"-thin\.svg$"),
            ("light",   "细线", r"-light\.svg$"),
            ("bold",    "粗体", r"-bold\.svg$"),
            ("fill",    "填充", r"-fill\.svg$"),
            ("duotone", "双色", r"-duotone\.svg$"),
            ("regular", "常规", r"\.svg$"),
        ],
        "fallback_variant": "regular",
        "categories": None,
    },
    {
        # MingCute 仅 line/fill 两种形态。显式登记避免 line-fill / chart-line-fill
        # 等"图标名含风格词"的文件被误判成 14 个虚假复合形态。
        "dir": "MingCute Icon", "name": "MingCute Icon",
        "file": "icons-mingcute-icon.json",
        "variants": [
            ("line", "线性", r"-line\.svg$"),
            ("fill", "填充", r"-fill\.svg$"),
        ],
        "fallback_variant": "line",
        "categories": None,
    },
    {
        # Remix Icon 主形态 line/fill；Logos 分类下的品牌图标没有形态后缀，
        # 用 default 兜底（之前误判 14 个虚假复合形态）。
        "dir": "Remix Icon", "name": "Remix Icon",
        "file": "icons-remix-icon.json",
        "variants": [
            ("line",    "线性", r"-line\.svg$"),
            ("fill",    "填充", r"-fill\.svg$"),
            ("default", "默认", r"\.svg$"),
        ],
        "fallback_variant": "default",
        "categories": None,
    },
    {
        # Simple Icons 是品牌 logo 集，每个 slug 对应唯一品牌（无形态）。
        # 显式登记成单形态、空分类：避免自动检测把品牌名 Outline/Linear/Solid/Ghost 等
        # 误判为形态后缀；品牌天然按字母索引查找，不需要关键词分类。
        "dir": "Simple Icons", "name": "Simple Icons",
        "file": "icons-simple-icons.json",
        "variants": [("default", "默认", r"\.svg$")],
        "fallback_variant": "default",
        "categories": [],
    },
]

# 分类：每个分类是 (中文名, 关键词列表)。匹配按顺序进行，先匹配到的优先。
# 用 startswith / contains 模糊匹配。contains 风险较大，关键词尽量具体。
CATEGORIES = [
    ("数字与字母", ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], "startswith_digit"),
    ("数字与计数", ["counter", "speed", "mp", "fps", "numbers", "number", "digit", "rating"], "any"),
    ("导航箭头", ["arrow", "chevron", "back", "forward", "expand", "collapse", "unfold", "left", "right", "up-", "down-", "east", "west", "north", "south", "near-me", "navigation", "directions"], "any"),
    ("媒体影像", ["image", "photo", "camera", "video", "movie", "film", "music", "audio", "play", "pause", "microphone", "mic", "gallery", "picture", "media", "lyrics", "podcasts", "radio", "volume", "sound", "speaker", "headphones", "earbuds", "in-ear", "subtitles", "stream", "subwoofer", "pip", "av1", "avc", "hevc", "hls", "rtt", "mms", "rss", "equalizer", "panorama", "screenshot", "screen-record", "gif", "hd", "full-hd", "high-res", "high-quality", "vr180", "vrpano", "amp-stories", "art-track", "comic-bubble", "manga", "genres", "piano", "piano-off",
        # 摄影分辨率（百万像素）
        "2mp","3mp","4mp","5mp","6mp","7mp","8mp","9mp","10mp","11mp","12mp","13mp","14mp","15mp","16mp","17mp","18mp","19mp","20mp","21mp","22mp","23mp","24mp","50mp",
        # 显示分辨率 K
        "1k","1k-plus","2k","2k-plus","3k","3k-plus","4k","4k-plus","5k","5k-plus","6k","6k-plus","7k","7k-plus","8k","8k-plus","9k","9k-plus","10k",
        # 视频帧率
        "24fps","30fps","60fps","24fps-select","30fps-select","60fps-select",
        # 全景 / VR / AR
        "360","vrpano","vr180-create2d","vr180-create2d-off","ar-on-you",
        # 播放控制：倍速
        "speed","speed-0-25","speed-0-2x","speed-0-5","speed-0-5x","speed-0-75","speed-0-7x","speed-1-2","speed-1-25","speed-1-2x","speed-1-5","speed-1-5x","speed-1-75","speed-1-7x","speed-2","speed-2x","speed-3","speed-4",
        # 播放控制：跳转
        "forward-5","forward-10","forward-30","forward-media","forward-circle","fast-forward","fast-rewind","skip-next","skip-previous","replay","replay-5","replay-10","replay-30","replay-circle-filled","slow-motion-video","closed-caption","closed-caption-add","closed-caption-disabled",
        # 摄影夜景 / 运动 / 视频博客
        "motion-photos-auto","motion-photos-on","motion-photos-paused","night-sight-auto","night-sight-auto-off","night-sight-max","auto-videocam","auto-stories","auto-stories-off","graphic-eq","graphic-eq-off","youtube-activity","youtube-activity-2","youtube-searched-for","iframe","iframe-off",
    ], "any"),
    ("设备硬件", ["phone", "laptop", "tablet", "desktop", "monitor", "keyboard", "mouse", "printer", "print", "fax", "watch", "device", "tv", "speaker", "router", "memory", "usb", "bluetooth", "wifi", "signal-cellular", "battery", "cast", "nfc", "sd-", "sim-", "remote", "hard-disk", "hardware", "cable", "host", "dvr", "modem", "settop", "trackpad", "scanner", "edgesensor", "sensor", "trackpad", "mobile", "screen-rotation", "chrome", "dock", "computer", "ios", "aod", "edgesensor-high", "edgesensor-low", "jamboard", "infrared", "vr", "headset", "tty", "apk-install", "apk-document", "devices", "phonelink", "flashlight", "doorbell", "app-blocking", "app-promo", "app-registration", "app-shortcut", "app-spark"], "any"),
    ("通讯消息", ["mail", "message", "chat", "forum", "comment", "send", "email", "inbox", "draft", "forward", "reply", "post", "sms", "contact", "social", "share", "link", "call", "sip", "dialer", "communication", "conversation", "dialog", "mms", "notifications","notifications-active","notifications-off","notifications-paused","notifications-unread","business-messages"], "any"),
    ("文件文件夹", ["file", "folder", "attach", "upload", "download", "document", "archive", "drive", "restore", "assignment", "description", "grading", "docs", "csv", "ods", "odt", "pdf", "page", "topic", "subject", "subheader", "title", "draft", "summarize", "essay", "quiz", "request-page", "submission", "rubric", "task", "notes", "note", "notebook", "pages", "article", "spreadsheet", "sheets-rtl", "request-quote", "request", "forms"], "any"),
    ("用户账号", ["person", "user", "account", "face", "human", "group", "groups", "groups-2", "groups-3", "crowd", "friend", "manage", "member", "sick", "pregnant", "badge", "crew", "supervisor", "engineering", "profile", "guardian", "support-agent", "assistant", "concierge", "agent", "co-present", "partner", "actor", "recent-actors"], "any"),
    ("人物形象", ["man", "woman", "female", "male", "boy", "girl", "child", "baby", "agender", "transgender", "elder", "elderly", "family", "demography", "diversity", "accessibility", "pregnancy", "e911-avatar", "people", "minor", "spokesman", "6-ft-apart"], "any"),
    ("编辑文本", ["edit", "draw", "text", "font", "pen", "pencil", "brush", "format", "align", "color", "palette", "strikethrough", "underline", "italic", "bold", "highlight", "spellcheck", "translate", "table-chart", "titlecase", "lowercase", "uppercase", "subscript", "superscript", "margin", "opacity", "glyphs", "serif", "sort", "sort-by-alpha", "signature", "sticker", "sticky-note", "stylus-note", "regular-expression", "match-case", "match-word", "custom-typography", "special-character"], "any"),
    ("时间日期", ["clock", "time", "hour", "alarm", "calendar", "schedule", "date", "history", "timer", "stopwatch", "sandglass", "pending", "event", "today", "next-week", "reminder", "rsvp", "things-to-do", "snooze", "last-page", "first-page", "recent"], "any"),
    ("状态反馈", ["check", "done", "close", "cancel", "error", "fail", "success", "sync", "refresh", "update", "save", "verified", "loading", "progress", "offline", "online", "publish", "draft", "undo", "redo", "remove", "cached", "cache", "hide", "show", "enable", "disable", "restart", "reset", "deselect", "select", "mark-as-unread", "thread-unread", "read-more", "restart-alt", "autorenew", "do-not-disturb", "stop", "repeat", "repeat-on", "repeat-one", "repeat-one-on", "resume", "unpublished", "unsubscribe", "upcoming", "orders", "order-approve", "inactive-order", "unsubscribe", "autostop", "track-changes", "exit-to-app", "unpublished", "full-coverage", "captured", "capture", "hourglass", "hourglass-bottom","hourglass-disabled","hourglass-empty","hourglass-full","hourglass-top","switch","switch-access","switch-access-2","switch-access-3","switch-access-shortcut","switch-off","keep","keep-off","keep-public","approval","approval-delegation","approval-delegation-off"], "any"),
    ("设置工具", ["settings", "config", "tune", "adjust", "build", "construction", "tool", "wrench", "hammer", "screw", "key-", "plumbing", "carpenter", "handyman", "extension", "menu", "more"], "any"),
    ("商务购物", ["shop", "store", "cart", "money", "dollar", "pay", "cash", "bank", "credit", "wallet", "receipt", "gift", "currency", "percent", "price", "label", "tag", "storefront", "shopping", "sell", "trophy", "leaderboard", "medal", "atm", "euro", "finance", "ballot", "monetization", "mintmark", "loyalty", "redeem", "paid", "point-of-sale", "toll", "production-quantity-limits", "real-estate-agent", "tenancy", "corporate", "campaign", "brand-awareness", "rewarded-ads", "reviews", "performance-max", "18-up-rating","rating", "bid-landscape","bid-landscape-disabled","business-center","contactless","contactless-off","personal-bag","personal-bag-off"], "any"),
    ("房屋家居", ["home", "house", "building", "roof", "bed", "chair", "sofa", "door", "window", "bath", "kitchen", "room", "appliance", "furniture", "cottage", "cabin", "balcony", "garage", "warehouse", "factory", "apartment", "air-purifier", "blender", "dishwasher", "microwave", "kettle", "fridge", "oven", "fan", "curtains", "blinds", "iron", "candle", "lightbulb", "lamp", "skillet", "stockpot", "styler", "range-hood", "refrigerator", "sprinkler", "faucet", "shower", "roller-shades", "shades", "crib", "tatami-seat", "countertops", "stove", "laundry", "dry-cleaning", "cleaning", "cookware", "flatware", "fork-spoon", "tabletop", "chair-alt", "mode-heat", "mode-cool", "mode-fan", "mode-heat-cool", "mode-heat-off", "mode-cool-off", "mode-fan-off", "mode-dual", "hvac", "nest-", "flourescent", "fluorescent", "light-mode", "light-off", "light", "light-group", "light-group-2", "wc", "wall-art", "wallpaper", "front-loader", "ac-unit", "fire-hydrant", "fire-extinguisher", "conveyor-belt", "wash", "vacuum", "styler", "dirty-lens", "bedtime", "bedtime-off", "backlight-high", "backlight-high-off", "backlight-low", "backlight"], "any"),
    ("建筑场所", ["mosque", "museum", "church", "synagogue", "temple", "stadium", "theater", "hotel", "bungalow", "cabin", "chalet", "castle", "fort", "foundation", "gate", "fence", "balcony", "pergola", "brick", "deck", "mall", "spa", "onsen", "beach", "pool", "sauna", "hot-tub", "nightlife", "festival", "camping", "attractions", "rest-area", "short-stay", "podium", "plaza", "hallway", "stairs", "elevator", "funeral", "wedding", "rsvp", "amusement", "tour", "rv-hookup", "night-shelter", "holiday-village", "bungalow", "villa", "deck"], "any"),
    ("交通出行", ["car", "bus", "train", "plane", "bike", "truck", "rocket", "ship", "boat", "flight", "directions", "route", "traffic", "fuel", "gas", "electric", "ev-", "tram", "taxi", "subway", "two-", "moped", "motorcycle", "wagon", "transit", "commute", "airplane", "scooter", "stroller", "forklift", "helicopter", "ambulance", "metro", "monorail", "funicular", "gondola-lift", "cable-car", "drone", "sailing", "cruise", "ferry", "no-transfer", "no-luggage", "multiple-stop", "mode-of-travel", "transportation", "travel", "tire-repair", "road", "lane", "minor-crash", "no-crash", "airlines", "airport", "connecting-airports", "multiple-airports", "departure-board", "rv-hookup", "trolley", "luggage", "moving", "your-trips", "flyover", "outbound", "nordic-walking",
        # 航空座位 / 行李 / 挡风玻璃 / 停车 / 拖车
        "airline-seat-flat","airline-seat-flat-angled","airline-seat-individual-suite","airline-seat-legroom-extra","airline-seat-legroom-normal","airline-seat-legroom-reduced","airline-seat-recline-extra","airline-seat-recline-normal","airline-stops","airline",
        "carry-on-bag","carry-on-bag-checked","carry-on-bag-inactive",
        "windshield-defrost-auto","windshield-defrost-front","windshield-defrost-rear","windshield-heat-front","windshield",
        "parking-meter","parking-sign","parking-valet","parking",
        "auto-towing","no-backpack","trolley","trailer",
    ], "any"),
    ("天气自然", ["weather", "cloud", "rain", "snow", "sun", "moon", "storm", "wind", "thunder", "water", "umbrella", "flood", "forest", "tree", "plant", "grass", "park", "earth", "eco", "energy", "sunny", "fog", "tornado", "humidity", "lightning", "hail", "landslide", "mountain", "beach", "salinity", "altitude", "recycling", "co2", "propane", "agriculture", "nature", "air", "severe-cold", "avalanche", "thermometer", "fertile", "specific-gravity", "total-dissolved-solids", "thermometer-gain", "thermometer-loss", "thermometer-minus", "earthquake", "volcano", "thermometer-add"], "any"),
    ("食品饮料", ["food", "drink", "restaurant", "coffee", "tea", "wine", "beer", "cake", "fruit", "rice", "burger", "pizza", "kitchen", "ramen", "dining", "liquor", "bar", "bakery", "dinner", "breakfast", "lunch", "grocery", "meal", "icecream", "cooking", "okonomiyaki", "soba", "sushi", "festival", "hanami-dango", "japanese-curry", "shaved-ice", "soup", "noodle", "skillet", "stockpot", "soap", "cocktail", "dine-in", "dine-lamp", "toast", "champagne", "sake", "soy-sauce"], "any"),
    ("动物植物", ["dog", "cat", "bird", "fish", "pet", "paw", "feather", "insect", "bug", "cruelty", "rabbit", "raven", "crisis", "bat", "spider", "horse", "pets", "pest-control", "skeleton", "bone", "skull", "hive", "honey"], "any"),
    ("医疗健康", ["health", "medical", "hospital", "doctor", "medicine", "heart", "pulse", "blood", "vaccine", "monitor-heart", "therapy", "dental", "eye-", "visibility", "hearing", "wheelchair", "elderly", "baby", "sick", "medication", "dermatology", "endocrinology", "gynecology", "hematology", "neurology", "nephrology", "oncology", "ophthalmology", "psychiatry", "rheumatology", "pulmonology", "podiatry", "ecg", "glucose", "metabolism", "respiratory", "stethoscope", "syringe", "symptoms", "surgical", "mixture-med", "clinical-notes", "recent-patient", "procedure", "inpatient", "spo2", "tibia-alt", "humerus-alt", "femur-alt", "oral-disease", "psychology", "cognition", "assistant-direction", "diet", "health-and-safety", "medication-liquid", "cannabis", "asa", "iron", "fitness-center", "vital-signs", "vitals", "oxygen-saturation", "ventilator", "vo2-max", "urology", "outpatient", "inpatient", "diagnosis", "clinical", "chronic", "wounds-injuries", "surgery", "undereye", "wrist", "ulna-radius-alt", "body-fat", "body-system", "hr-resting", "ventilation", "allergy", "allergies", "eyeglasses", "recent-patient", "other-admission", "inpatient", "sauna", "flaky", "cool-to-dry", "ward"], "any"),
    ("警示通知", ["notification", "alert", "warning", "info", "help", "question", "issue", "badge", "flag", "priority", "emergency", "crisis", "announcement", "release", "dangerous", "explosion", "bomb", "sos", "problem", "siren", "alert", "broken", "danger", "gpp-bad", "gpp-maybe", "gpp-good", "fmd-bad", "disc-full", "whatshot", "troubleshoot", "destruction"], "any"),
    ("安全锁", ["security", "lock", "shield", "password", "login", "logout", "fingerprint", "vpn", "encrypted", "verified-user", "policy", "spam", "block", "ban", "privacy", "phishing", "spoof", "no-encryption", "enhanced-encryption", "private-connectivity", "identity", "passkey", "captcha", "key","key-off","key-vertical","key-visualizer"], "any"),
    ("游戏运动", ["game", "sport", "casino", "dice", "poker", "joystick", "controller", "football", "basketball", "soccer", "tennis", "gaming", "sports", "esports", "score", "scoreboard", "kayaking", "snowboarding", "skiing", "surfing", "skate", "chess", "badminton", "fitness", "golf", "hiking", "ice-skating", "nordic-walking", "padel", "paragliding", "pickleball", "roller-skating", "scuba-diving", "sledding", "kayak", "sprint", "kendo", "swords", "sword-rose", "taunt", "gun", "target", "stadium", "racquet", "joystick-alt", "fan-focus", "sabre", "medal"], "any"),
    ("AI与技术", ["robot", "smart", "code", "developer", "terminal", "deploy", "cloud", "server", "database", "network", "integration", "api", "memory-alt", "python", "javascript", "html", "css", "schema", "biotech", "smart-display", "smart-tout", "neurology", "http", "lan", "sdk", "php", "sql", "p2p", "nat", "cookie", "rss", "prompt-suggestion", "token", "tokens", "contextual-token", "generating-tokens", "cookie-off", "memory-alt", "stack", "stacks", "stack-off", "smart-phone", "smart-tout"], "any"),
    ("图形形状", ["shape", "circle", "square", "triangle", "polygon", "star", "hexagon", "line", "dash", "dot", "ring", "scatter", "vertical", "horizontal", "diagonal", "rectangle", "oval", "diamond", "pentagon", "octagon", "ruler", "rounded-corner", "asterisk", "exclamation", "equal", "star", "polygon", "bubble", "bubbles", "cube", "pyramid", "cylinder",
        # 2D/3D 维度
        "2d","2d-2","3d","3d-2","3d-rotation",
    ], "any"),
    ("地图位置", ["map", "location", "place", "pin", "gps", "compass", "geo", "satellite", "terrain", "near", "local", "region", "trail", "trail-length", "trail-length-medium", "trail-length-short", "streetview", "beenhere", "follow-the-signs", "fmd-bad", "where-to-vote", "how-to-vote", "how-to-reg", "located", "recenter", "location-on", "add-location", "navigation"], "any"),
    ("教育与科学", ["school", "science", "book", "study", "lab", "experiment", "formula", "function", "research", "teacher", "student", "library", "knowledge", "dictionary", "calculator", "psychology", "philosophy", "quiz", "grade", "grading", "rubric", "school", "presentation", "science-off", "interpreter-mode", "mindfulness", "self-improvement", "stances", "tactic", "strategy", "trending-up", "trending-down", "trending-flat", "calculation"], "any"),
    ("情感与表情", ["mood", "feeling", "emoji", "emoticon", "smile", "sad", "happy", "love", "favorite", "thumb", "like", "dislike", "sentiment", "emotion", "facial", "heart", "cheer", "celebration", "relax", "sleep", "comedy-mask", "theater-comedy", "satisfaction", "angry", "excited", "masks", "lips", "owl", "mystery"], "any"),
    ("容器布局", ["view", "list", "grid", "frame", "tab", "splitscreen", "border", "table", "dashboard", "apps", "widget", "card", "panel", "layout", "column", "row", "module", "puzzle", "module", "tile", "segment", "layers", "deck", "pageless", "toc", "subheader", "reorder", "shift", "stack", "margin", "footer", "header", "page-footer", "page-header", "sidebar", "subheader", "design-services", "trending", "fit", "fit-page", "fit-width", "fit-screen", "maximize", "minimize", "fullscreen", "fullscreen-exit", "magnification", "magnify", "pan-zoom", "zoom", "scale", "resize", "aspect-ratio", "flex-direction", "flex-no-wrap", "flex-wrap", "density-large", "density-medium", "density-small", "density", "float-landscape", "float-portrait", "stay-primary-portrait", "vignette", "workspace-premium", "dark-mode", "high-density", "low-density", "input", "output"], "any"),
    ("图像编辑", ["filter", "crop", "rotate", "blur", "exposure", "brightness", "flash", "hdr", "looks", "ink", "healing", "duotone", "gradient", "auto-fix", "tonality", "shutter", "aperture", "iso", "raw-on", "raw-off", "contrast-rtl-off", "reset-focus", "reset-shadow", "reset-white-balance", "portrait-lighting", "portrait-lighting-off", "burst-mode", "auto-awesome", "auto-awesome-motion", "magic-exchange", "magic-tether", "macro-auto", "macro-off", "loupe", "flip", "flip-to-front", "transform", "straighten", "straight", "dehaze", "flare",
        # 白平衡
        "wb-auto","wb-incandescent","wb-iridescent","wb-shade","wb-sunny","wb-twilight","wb-twilight-2",
        # 视频转场 / 颜色反转
        "transition-chop","transition-fade","transition-push","invert-colors","invert-colors-off",
    ], "any"),
    ("数据图表", ["chart", "graph", "data", "stat", "analytics", "insights", "leaderboard", "timeline", "query", "monitoring", "report", "savings", "donut", "heap-snapshot", "legend-toggle", "simulation", "flowsheet", "demography", "source-environment", "stacked-bar-chart", "area-chart", "monitoring", "assured-workload", "flow", "trail-length"], "any"),
    ("搜索查找", ["search", "find", "browse", "lookup", "query", "explore", "discover", "radar", "scan", "scanner", "detect", "detector", "sensors", "find-in-page", "find-location", "search-off", "lasso-select", "jump-to-element", "find-replace", "explore", "near-me"], "any"),
    ("添加删除", ["add", "delete", "remove", "clear", "drag", "drop", "swap", "move", "content", "copy", "cut", "paste", "merge", "join", "split", "filter", "reorder", "rebase", "repartition", "sweep", "cycle", "commit", "compare", "compress", "contrast", "shrink", "delete-sweep", "shift", "step", "step-into", "step-out", "step-over", "skip-next", "skip-previous", "shuffle"], "any"),
    ("语言文字", ["language", "translate", "abc", "dialpad", "keyboard", "alphabet", "letter", "markdown", "spell", "letter", "format-list", "translate", "kanji", "text", "font"], "any"),
    ("电源能源", ["power", "energy", "battery", "charging", "charge", "plug", "outlet", "solar", "ev-", "fuel", "gas", "propane", "solar-power", "gas-meter", "3p"], "any"),
    ("手势触摸", ["touch", "hand", "finger", "tap", "swipe", "gesture", "drag", "pinch", "scroll", "pointer", "cursor", "mouse", "paw", "sign-language", "back-hand", "lift-to-talk", "select-to-speak", "record-voice-over", "voice-over", "wave", "high-five"], "any"),
    ("实验科学", ["science", "lab", "experiment", "biotech", "flask", "microscope", "telescope", "physics", "chemistry", "atom", "molecule", "formula", "genetics", "particle", "experiment", "function"], "any"),
    ("容器存储", ["box", "container", "jar", "bottle", "package", "inventory", "warehouse", "storage", "archive", "pallet", "pail", "shelves", "chest", "stockpot"], "any"),
    ("媒体出版", ["news", "newspaper", "newsstand", "newsmode", "breaking-news", "amp-stories", "article", "blog", "feed", "rss-feed", "subscriptions", "comic", "manga", "art-track", "artist", "celebration", "podcast", "magazine", "broadcast", "broadcast-on-home", "broadcast-on-personal"], "any"),
    ("政府法律", ["gavel", "ballot", "license", "policy", "permit", "guard", "military-tech", "guardian", "policy", "rule", "law", "tenancy", "policy", "synagogue", "church", "mosque", "temple", "rsvp", "corporate-fare", "enterprise", "verified-user", "convention"], "any"),
    ("网络协议", ["http", "lan", "vpn", "hls", "hls-off", "av1", "avc", "hevc", "mimo", "dns", "ipv", "sdk", "php", "sql", "p2p", "nat", "cookie", "rss", "ipv6", "ipv4", "udp", "tcp", "domain", "domain-verification", "captive-portal", "webhook", "polymer", "web-asset-off", "ats", "cell-tower",
        # 移动通讯代
        "5g","1x-mobiledata","1x-mobiledata-badge","3g-mobiledata","3g-mobiledata-badge","4g-mobiledata","4g-mobiledata-badge","4g-plus-mobiledata","5g-mobiledata-badge","lte-mobiledata","lte-plus-mobiledata","mobiledata-arrows","mobiledata-off",
    ], "any"),
    ("声音语音", ["voice", "audio", "sound", "speech", "narration", "mic", "voice-over", "record-voice-over", "transcribe", "interpreter", "speech-to-text", "speaker", "subtitle", "subtitles", "voice-", "assist-walker"], "any"),
]


def load_manifest():
    """加载 folder_name -> iconify prefix 映射。文件缺失或损坏返回空 dict。"""
    if not os.path.isfile(MANIFEST_PATH):
        return {}
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def fetch_official_categories(prefix):
    """从 Iconify API 拉取某 prefix 的分类信息（/collection?prefix=X 的子集）。"""
    url = f"https://api.iconify.design/collection?prefix={prefix}"
    req = Request(url, headers={"User-Agent": "SvgResourcesIndexBuilder/1.0"})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "prefix": prefix,
        "total": data.get("total", 0),
        "categories": data.get("categories", {}),
        "uncategorized": data.get("uncategorized", []),
        "aliases": data.get("aliases", {}),
    }


def load_official_categories(prefix, refresh=False):
    """返回 (cat_order, name_to_cats) 或 None。

    cat_order     —— 官方分类名的原始顺序（用于稳定展示）
    name_to_cats  —— {icon_name: [cat1, cat2, ...]}，已展开别名映射

    缓存命中规则：默认读 Themes/_iconify-categories/<prefix>.json；
    refresh=True 或缓存不存在则联网拉取并写盘。
    若该 prefix 没有官方分类（categories 为空）返回 None，调用方回退到关键词匹配。
    """
    if not prefix:
        return None
    os.makedirs(CAT_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CAT_CACHE_DIR, f"{prefix}.json")
    data = None
    if not refresh and os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = None
    if data is None:
        try:
            data = fetch_official_categories(prefix)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except (HTTPError, URLError, OSError) as e:
            print(f"  [warn] 拉取 {prefix} 官方分类失败：{e}")
            return None
    cats = data.get("categories", {})
    if not cats:
        return None
    name_to_cats = {}
    for cat_name, icons in cats.items():
        for icon in icons:
            name_to_cats.setdefault(icon, []).append(cat_name)
    # 别名展开：alias 继承 real 名的分类
    for alias, real in data.get("aliases", {}).items():
        if real in name_to_cats:
            name_to_cats[alias] = name_to_cats[real]
    return list(cats.keys()), name_to_cats


def match_categories(name, categories=CATEGORIES):
    """返回该 name 所属的所有分类中文名列表（多标签，去重保序）。未匹配返回空列表。

    匹配规则：
    - 前缀型关键词（以 '-' 结尾，如 'ev-'、'key-'、'sd-'）：要求词元以该前缀开头
    - 普通关键词：要求作为完整词元出现（前后都被 '-' 或字符串边界包裹）
      这样可避免 'ear' 命中 'gear'、'light' 命中 'flight'、'air' 命中 'airplane' 等子串误匹配
    """
    matched = []
    seen = set()
    wrapped = f"-{name}-"
    for cat_name, keywords, mode in categories:
        hit = False
        if mode == "startswith_digit":
            if name and name[0].isdigit():
                hit = True
        else:
            for kw in keywords:
                if kw.endswith("-"):
                    # 前缀型：词元以 kw 开头
                    if name.startswith(kw) or f"-{kw}" in wrapped:
                        hit = True
                        break
                else:
                    # 完整词元：前后都加边界，杜绝子串误命中
                    if f"-{kw}-" in wrapped or name == kw:
                        hit = True
                        break
        if hit and cat_name not in seen:
            seen.add(cat_name)
            matched.append(cat_name)
    return matched


def extract_variant(basename, variants, fallback_variant):
    """返回 (variant_key, icon_name)。

    按 variants 顺序试每个结尾后缀正则；第一个命中者决定 variant，
    图标名 = 命中位置之前的子串（已同时去掉后缀与 .svg）。
    都不命中则 variant=fallback_variant，图标名 = 去掉 .svg。
    """
    for key, _label, suffix_re in variants:
        m = re.search(suffix_re, basename)
        if m:
            return key, basename[:m.start()]
    return fallback_variant, re.sub(r"\.svg$", "", basename)


# 不作为主题扫描的目录（备选区、文档、版本控制等）
EXCLUDE_DIRS = {"Picked", "docs", ".git", ".claude"}

# 已知「形态」关键词：出现在文件名末尾、表示风格而非图标名的一部分。
# 仅当它们在整目录里大规模成簇出现（坍缩率高）时才认定为形态后缀，
# 零星出现（如某主题里恰好有 foo 与 foo-bold 两个独立图标）不会触发误判。
STYLE_KEYWORDS = {
    "filled", "fill", "regular", "outline", "linear", "bold", "broken", "light",
    "thin", "duotone", "solid", "twotone", "two-tone", "rounded", "sharp",
    "line", "bulk", "monotone", "ghost", "alt",
}
STYLE_LABELS = {
    "filled": "填充", "fill": "填充", "regular": "线性", "outline": "描边",
    "linear": "线性", "bold": "粗体", "broken": "破碎", "light": "细线",
    "thin": "特细", "duotone": "双色", "solid": "实心", "twotone": "双色",
    "two-tone": "双色", "rounded": "圆角", "sharp": "锐利", "line": "线性",
    "bulk": "体积", "monotone": "单色", "ghost": "幽灵", "alt": "变体",
}
# 判定为多形态的坍缩率门槛：base 名拥有 ≥2 个形态文件的比例需达到此值。
COLLAPSE_THRESHOLD = 0.25
# 走「数字尺寸+风格」分支的匹配率门槛：必须有相当比例的文件符合该模式，
# 否则零星含数字的图标名（如 Solar 的 home-2-bold）会误触发。
SIZE_MATCH_RATE = 0.6


def _variant_label(variant_str):
    """给形态串取中文标签：取其中首个已知关键词的标签，找不到就用原文。"""
    for tok in variant_str.split("-"):
        if tok in STYLE_LABELS:
            return STYLE_LABELS[tok]
    return variant_str


def detect_variants(basenames):
    """分析一组文件名，自动判断是否为多形态主题。

    返回 (variants, fallback_variant)：
      - variants = [(key, 中文标签, 后缀正则), ...]，按后缀长度降序排列
        （长复合后缀优先匹配，避免 -rounded 抢先吃掉 -outline-rounded）；
      - 判定为单形态时返回 (None, None)。

    检测按优先级尝试两种模式，均不满足则视为单形态：
      1) 数字尺寸 + 风格：<base>-<数字>-<风格>.svg（如 camera-24-filled）
         —— 尾部 -数字- 几乎不可能是图标名的一部分，几乎无歧义，优先。
      2) 末尾形态关键词：从尾部贪婪吃掉连续的已知关键词作为形态，
         支持复合（outline-rounded / bold-duotone）。
    两种模式都用「坍缩率」把关：只有大量图标能合并到同一 base 时才认定。
    """
    def collapse_rate(pairs):
        bases = defaultdict(set)
        for base, var in pairs:
            bases[base].add(var)
        if not bases:
            return 0.0
        return sum(1 for vs in bases.values() if len(vs) >= 2) / len(bases)

    def with_default(variants, plain_count, fallback):
        """若存在未被任何形态正则匹配的"无后缀"文件，追加一个放最后的"默认"形态
        （正则 \\.svg$ 兜底），并让 fallback 指向它。这样如 Phosphor 的
        airplane.svg（regular 无后缀）不会和 airplane-thin.svg 撞到同一形态槽。"""
        if plain_count > 0:
            variants = variants + [("default", "默认", r"\.svg$")]
            return variants, "default"
        return variants, fallback

    # 候选 1：数字尺寸 + 风格 <base>-<尺寸>-<风格>.svg
    # 关键：形态词必须显式属于已知风格集，否则名字里夹的数字会被误当尺寸
    # （如 calendar-3-day-16-filled 里的 "3"）。显式风格锚定后，惰性匹配会落到
    # 最后一个"真正的 尺寸-风格"上。
    style_alt = "|".join(sorted(STYLE_KEYWORDS, key=len, reverse=True))
    size_re = re.compile(rf"^(.*?)-(\d+)-({style_alt})\.svg$")
    size_pairs = []
    for b in basenames:
        m = size_re.match(b)
        if m:
            size_pairs.append((m.group(1), m.group(3)))
    if (size_pairs
            and len(size_pairs) / len(basenames) >= SIZE_MATCH_RATE
            and collapse_rate(size_pairs) >= COLLAPSE_THRESHOLD):
        styles = sorted({v for _, v in size_pairs}, key=len, reverse=True)
        variants = [(s, STYLE_LABELS.get(s, s), rf"-\d+-{re.escape(s)}\.svg$")
                    for s in styles]
        fallback = Counter(v for _, v in size_pairs).most_common(1)[0][0]
        return with_default(variants, len(basenames) - len(size_pairs), fallback)

    # 候选 2：末尾形态关键词（支持复合）
    kw_pairs = []
    matched = 0
    for b in basenames:
        name = b[:-4] if b.lower().endswith(".svg") else b
        toks = name.split("-")
        i = len(toks)
        while i > 0 and toks[i - 1] in STYLE_KEYWORDS:
            i -= 1
        if i < len(toks):
            kw_pairs.append(("-".join(toks[:i]), "-".join(toks[i:])))
            matched += 1
    if kw_pairs and collapse_rate(kw_pairs) >= COLLAPSE_THRESHOLD:
        var_strs = sorted({v for _, v in kw_pairs}, key=len, reverse=True)
        variants = [(v, _variant_label(v), rf"-{re.escape(v)}\.svg$")
                    for v in var_strs]
        fallback = Counter(v for _, v in kw_pairs).most_common(1)[0][0]
        return with_default(variants, len(basenames) - matched, fallback)

    return None, None


def discover_extra_themes(curated_dirs):
    """自动发现：扫描 THEMES_DIR 下未被 THEMES 收录、且含 .svg 的子目录，
    自动判定形态后登记为主题。

    这样"下载一个新图标集 → 丢进 Themes/ → 重建索引"即可自动出现在预览页，
    无需手工编辑 THEMES——包括多形态主题（会由 detect_variants 自动识别）。
    """
    extra = []
    if not os.path.isdir(THEMES_DIR):
        return extra
    for entry in sorted(os.listdir(THEMES_DIR)):
        full = os.path.join(THEMES_DIR, entry)
        if entry.startswith(".") or entry in EXCLUDE_DIRS or entry in curated_dirs:
            continue
        if not os.path.isdir(full):
            continue
        try:
            svgs = [f for f in os.listdir(full) if f.endswith(".svg")]
        except OSError:
            continue
        if not svgs:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", entry.lower()).strip("-") or "extra"
        variants, fallback = detect_variants(svgs)
        if variants is None:
            # 单形态主题
            variants_cfg = [("default", "默认", r"\.svg$")]
            fallback = "default"
        else:
            variants_cfg = variants
        extra.append({
            "dir": entry, "name": entry,
            "file": f"icons-{slug}.json",
            "variants": variants_cfg,
            "fallback_variant": fallback,
            "categories": None,
        })
    return extra


def build_theme(theme, manifest=None, refresh_categories=False):
    """扫描单个主题目录，返回与原 icons.json 同构（但泛化）的结果字典。

    分类优先级：
      1) 主题目录在 manifest 里有 prefix，且该 prefix 拥有非空官方分类 → 用官方分类
      2) 否则用 cats_cfg（主题专属关键词或全局 CATEGORIES）做关键词匹配
    """
    if manifest is None:
        manifest = load_manifest()
    sub_dir = os.path.join(THEMES_DIR, theme["dir"])
    variants_cfg = theme["variants"]
    cats_cfg = theme["categories"] if theme["categories"] is not None else CATEGORIES

    # 尝试加载官方分类
    prefix = manifest.get(theme["dir"])
    official = load_official_categories(prefix, refresh=refresh_categories) if prefix else None
    classify_source = "official" if official else "keyword"

    # 收集相对路径（正斜杠）。排序以保证构建确定性；
    # 对多文件合并到同一图标名的主题（如 Fluent UI 的多尺寸），排序后"后赋值者胜"，
    # 尺寸按文件名升序处理，最终保留最大尺寸的源文件（矢量缩放后视觉一致）。
    files = []
    if os.path.isdir(sub_dir):
        for f in os.listdir(sub_dir):
            if f.endswith(".svg"):
                files.append(f"{theme['dir']}/{f}")
    files.sort()

    # name -> {variant_key: relpath}
    by_name = defaultdict(dict)
    for rel in files:
        base = os.path.basename(rel)
        vkey, name = extract_variant(base, variants_cfg, theme["fallback_variant"])
        by_name[name][vkey] = rel

    # 分类（多标签）
    categorized = defaultdict(list)
    uncategorized = []
    if official:
        cat_order, name_to_cats = official
        # Iconify API 的图标名通常带形态后缀（如 solar 的 "home-bold"、
        # mingcute 的 "home-line"），而 build 这边把后缀剥离成 name="home"。
        # 所以反查分类时要用各形态的原始文件名（去 .svg）来匹配，任一命中即采用。
        for name in sorted(by_name.keys()):
            vfiles = by_name[name]
            cats = None
            for rel in vfiles.values():
                stem = os.path.basename(rel)[:-4]  # 去 .svg
                if stem in name_to_cats:
                    cats = name_to_cats[stem]
                    break
            # 兜底：再试一次剥离后的 name（mdi / carbon 这类单形态主题用得上）
            if cats is None and name in name_to_cats:
                cats = name_to_cats[name]
            item = {"name": name, "files": vfiles}
            if cats:
                for c in cats:
                    categorized[c].append(item)
            else:
                uncategorized.append(item)
    else:
        cat_order = [c[0] for c in cats_cfg]
        for name in sorted(by_name.keys()):
            cats = match_categories(name, cats_cfg)
            item = {"name": name, "files": by_name[name]}
            for c in cats:
                categorized[c].append(item)
            if not cats:
                uncategorized.append(item)

    # 按首字母分组（用于 All 索引）
    alpha_groups = defaultdict(list)
    for name in sorted(by_name.keys()):
        first = name[0].upper()
        if first.isdigit():
            first = "#"
        alpha_groups[first].append({"name": name, "files": by_name[name]})

    # 整理 categories 顺序：官方按 API 返回顺序，关键词按定义顺序
    cats_out = []
    for cn in cat_order:
        items = categorized.get(cn, [])
        if items:
            cats_out.append({"name": cn, "count": len(items), "items": items})
    # 仅当主题拥有分类体系（cat_order 非空）时才追加"其他"承载离群图标。
    # categories: [] 显式表示"不分类"（如 Simple Icons 这种品牌 logo 集），
    # 此时全部图标只走字母索引，不再塞进一个巨大的"其他"分组里。
    if uncategorized and cat_order:
        cats_out.append({"name": "其他", "count": len(uncategorized), "items": uncategorized})

    alpha = [{"letter": k, "count": len(v), "items": v} for k, v in sorted(alpha_groups.items())]

    return {
        "total_icons": len(by_name),
        "total_files": len(files),
        "total_labels": sum(len(v) for v in categorized.values()),
        "variants": [{"key": k, "label": l} for k, l, _r in variants_cfg],
        "categories": cats_out,
        "alphabet": alpha,
        "all": [{"name": n, "files": by_name[n]} for n in sorted(by_name.keys())],
        "classify_source": classify_source,
    }


def main():
    os.makedirs(THEMES_DIR, exist_ok=True)
    refresh = "--refresh-categories" in sys.argv
    manifest = load_manifest()
    # THEMES = 显式配置的多形态/精选主题；再拼接自动发现的单形态主题
    all_themes = THEMES + discover_extra_themes({t["dir"] for t in THEMES})

    manifest_out = []
    for theme in all_themes:
        result = build_theme(theme, manifest=manifest, refresh_categories=refresh)
        out_path = os.path.join(THEMES_DIR, theme["file"])
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        manifest_out.append({
            "name": theme["name"],
            "file": theme["file"],
            "default": bool(theme.get("default", False)),
        })
        sz = os.path.getsize(out_path)
        print(f"[{theme['name']}] icons={result['total_icons']} files={result['total_files']} "
              f"variants={len(result['variants'])} labels={result['total_labels']} "
              f"classify={result['classify_source']} "
              f"-> Themes/{theme['file']} ({sz/1024:.1f} KB)")

    manifest_path = os.path.join(THEMES_DIR, "themes.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_out, f, ensure_ascii=False)
    print(f"Wrote {len(manifest_out)} themes -> Themes/themes.json")


if __name__ == "__main__":
    main()
