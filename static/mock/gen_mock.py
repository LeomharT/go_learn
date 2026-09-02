#!/usr/bin/env python3
# 生成障碍层对外数据流的 mock 帧，供前端离线联调。
# 编码链与 nav_egress 的 grid_index_codec 一致：升序索引 → 首元素绝对值其余差分 →
# 小端 u32 → gzip(RFC 1952) → base64。栅格行 0 在世界坐标下方，PGM 行 0 在图片顶部。
import base64
import json
import math
import os
import struct
import zlib
from collections import deque

MAP_DIR = "/Users/liangwushang/Downloads/16f01"
PGM = os.path.join(MAP_DIR, "16f01.pgm")
OUT = ("/Users/liangwushang/Documents/workspace/GS/catkin_ws/src/ros2-docker/"
       "docs/2026-08-28-feat-egress-obstacle-stream/mock")

RESOLUTION = 0.0500000007
ORIGIN = [-14.849349931483356, -3.4597200864653095]
OCCUPIED_THRESH = 0.5
FREE_THRESH = 0.19
INSCRIBED_RADIUS_M = 0.16          # footprint 半宽，决定层 B 的膨胀半径
FRAME_ID = "map"
STAMP0_SEC = 1787852919
STAMP0_NSEC = 970551314

os.makedirs(OUT, exist_ok=True)


# ---------- PGM 读取 ----------
def read_pgm(path):
    """解析 P5 二进制 PGM，返回 (宽, 高, 灰度数组)。灰度按文件顺序：行 0 在图片顶部。"""
    with open(path, "rb") as f:
        data = f.read()
    idx, tokens = 0, []
    while len(tokens) < 4:
        while data[idx:idx + 1].isspace():
            idx += 1
        if data[idx:idx + 1] == b"#":
            while data[idx:idx + 1] not in (b"\n", b"\r"):
                idx += 1
            continue
        start = idx
        while not data[idx:idx + 1].isspace():
            idx += 1
        tokens.append(data[start:idx])
    idx += 1
    w, h = int(tokens[1]), int(tokens[2])
    return w, h, data[idx:idx + w * h]


W, H, raster = read_pgm(PGM)
N = W * H

# ---------- 灰度 → 占据语义，并翻转成栅格行序（行 0 在下） ----------
# map_server trinary 规则（negate=0）：p = (255 - 像素) / 255
# p > occupied_thresh 为墙，p < free_thresh 为空闲，其余为未知
WALL, FREE, UNKNOWN = 1, 0, 2
cellkind = bytearray(N)
for r in range(H):
    src = (H - 1 - r) * W          # 栅格第 r 行 = 图片倒数第 r 行
    dst = r * W
    for c in range(W):
        p = (255 - raster[src + c]) / 255.0
        if p > OCCUPIED_THRESH:
            cellkind[dst + c] = WALL
        elif p < FREE_THRESH:
            cellkind[dst + c] = FREE
        else:
            cellkind[dst + c] = UNKNOWN


# ---------- 膨胀核：距离 ≤ 内切半径的格偏移 ----------
def disk_offsets(radius_m, res):
    lim = radius_m / res
    rr = int(math.floor(lim))
    offs = []
    for dy in range(-rr, rr + 1):
        for dx in range(-rr, rr + 1):
            if math.hypot(dx, dy) <= lim:
                offs.append((dx, dy))
    return offs


INFLATE = disk_offsets(INSCRIBED_RADIUS_M, RESOLUTION)


def dilate(seed_indices):
    """把种子格按内切半径膨胀，返回命中格集合（含种子本身）。"""
    out = set()
    for i in seed_indices:
        c0, r0 = i % W, i // W
        for dx, dy in INFLATE:
            c, r = c0 + dx, r0 + dy
            if 0 <= c < W and 0 <= r < H:
                out.add(r * W + c)
    return out


# ---------- 净空距离：每个空闲格到最近非空闲格的格数 ----------
def clearance_map():
    dist = [-1] * N
    q = deque()
    for i in range(N):
        if cellkind[i] != FREE:
            dist[i] = 0
            q.append(i)
    while q:
        i = q.popleft()
        c, r = i % W, i // W
        d = dist[i] + 1
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = c + dc, r + dr
            if 0 <= nc < W and 0 <= nr < H:
                j = nr * W + nc
                if dist[j] < 0:
                    dist[j] = d
                    q.append(j)
    return dist


CLEAR = clearance_map()


def pick_open_spots(count, min_clear_cells, min_apart_cells):
    """挑净空足够、彼此拉开距离的空闲格，作为临时障碍的落点。确定性：按净空降序、索引升序。"""
    cands = [i for i in range(N) if cellkind[i] == FREE and CLEAR[i] >= min_clear_cells]
    cands.sort(key=lambda i: (-CLEAR[i], i))
    picked = []
    for i in cands:
        c, r = i % W, i // W
        if all(math.hypot(c - pc, r - pr) >= min_apart_cells for pc, pr in picked):
            picked.append((c, r))
            if len(picked) == count:
                break
    return picked


def disk(cx, cy, radius_m):
    """以 (cx, cy) 为心画实心圆，返回格索引列表。"""
    out = []
    rr = int(math.floor(radius_m / RESOLUTION))
    for dy in range(-rr, rr + 1):
        for dx in range(-rr, rr + 1):
            if math.hypot(dx, dy) * RESOLUTION <= radius_m:
                c, r = cx + dx, cy + dy
                if 0 <= c < W and 0 <= r < H:
                    out.append(r * W + c)
    return out


def box(cx, cy, half_w_m, half_h_m):
    """以 (cx, cy) 为心画实心矩形，返回格索引列表。"""
    out = []
    hw = int(round(half_w_m / RESOLUTION))
    hh = int(round(half_h_m / RESOLUTION))
    for dy in range(-hh, hh + 1):
        for dx in range(-hw, hw + 1):
            c, r = cx + dx, cy + dy
            if 0 <= c < W and 0 <= r < H:
                out.append(r * W + c)
    return out


# ---------- 编码：索引 → u32delta+gzip+b64 ----------
def encode_cells(sorted_indices, level=6):
    buf = bytearray()
    prev = 0
    for k, v in enumerate(sorted_indices):
        d = v if k == 0 else v - prev
        prev = v
        buf += struct.pack("<I", d)
    co = zlib.compressobj(level, zlib.DEFLATED, 15 + 16)   # 15+16 = gzip 容器
    gz = co.compress(bytes(buf)) + co.flush()
    return base64.b64encode(gz).decode("ascii")


def payload(cells, layer, frame_no):
    idx = sorted(set(cells))
    return {
        "stamp": {"sec": STAMP0_SEC + frame_no, "nanosec": STAMP0_NSEC},
        "frame_id": FRAME_ID,
        "layer": layer,
        "region": {"col0": 0, "row0": 0, "width": W, "height": H},
        "resolution": RESOLUTION,
        "origin": ORIGIN,
        "encoding": "u32delta+gzip+b64",
        "count": len(idx),
        "data": encode_cells(idx),
    }


def dump(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    return path, os.path.getsize(path)


# ---------- 场景构造 ----------
walls = [i for i in range(N) if cellkind[i] == WALL]
spots = pick_open_spots(3, min_clear_cells=14, min_apart_cells=60)

# 未知区落点：找一个紧挨空闲区的未知格，模拟"地图上没有、但传感器看到了"的观测。
# 取离空闲区重心最近的那个，避免落在图边缘看起来像噪点。
free_cells = [i for i in range(N) if cellkind[i] == FREE]
gx = sum(i % W for i in free_cells) / len(free_cells)
gy = sum(i // W for i in free_cells) / len(free_cells)
unknown_spot, best_d = None, None
for i in range(N):
    if cellkind[i] != UNKNOWN:
        continue
    c, r = i % W, i // W
    if not (8 <= c < W - 8 and 8 <= r < H - 8):
        continue
    # 要离墙足够远，否则画出来像是压在墙上，看不出"未知区里的观测"这层意思
    if any(cellkind[(r + dr) * W + (c + dc)] == WALL
           for dr in range(-5, 6) for dc in range(-5, 6)):
        continue
    if not any(cellkind[(r + dr) * W + (c + dc)] == FREE
               for dr in range(-7, 8) for dc in range(-7, 8)):
        continue
    d = math.hypot(c - gx, r - gy)
    if best_d is None or d < best_d:
        unknown_spot, best_d = (c, r), d

(pc, pr) = spots[0]            # 行人 1，会移动
(qc, qr) = spots[1]            # 行人 2，站着不动
(bc, br) = spots[2]            # 临时堆放的箱子

FRAMES = 5
manifest = []

for k in range(FRAMES):
    person1 = disk(pc + k * 5, pr, 0.20)          # 每帧沿 +x 走 5 格 = 0.25 米
    person2 = disk(qc, qr, 0.18)
    carton = box(bc, br, 0.30, 0.40)
    cells = person1 + person2 + carton
    if unknown_spot:
        cells += disk(unknown_spot[0], unknown_spot[1], 0.15)
    p = payload(cells, "lethal", k)
    name = "obstacles_lethal_%02d.json" % (k + 1)
    manifest.append((name, dump(name, p), p["count"]))

# 空帧：count = 0，data 是可正常解码、解出零个元素的合法串
empty = payload([], "lethal", FRAMES)
manifest.append(("obstacles_lethal_empty.json",
                 dump("obstacles_lethal_empty.json", empty), empty["count"]))

# 层 B：墙 + 内切半径膨胀（静止场景）
blocked_static_cells = dilate(walls)
pb = payload(blocked_static_cells, "blocked", 0)
manifest.append(("obstacles_blocked.json", dump("obstacles_blocked.json", pb), pb["count"]))

# 层 B：叠上临时障碍及其膨胀（第 3 帧的场景）
temp3 = disk(pc + 2 * 5, pr, 0.20) + disk(qc, qr, 0.18) + box(bc, br, 0.30, 0.40)
pb2 = payload(blocked_static_cells | dilate(temp3), "blocked", 2)
manifest.append(("obstacles_blocked_with_temp.json",
                 dump("obstacles_blocked_with_temp.json", pb2), pb2["count"]))

# WS 信封格式，逐行一条，可直接喂给前端的 onmessage
with open(os.path.join(OUT, "ws_frames.jsonl"), "w", encoding="utf-8") as f:
    for k in range(FRAMES):
        with open(os.path.join(OUT, "obstacles_lethal_%02d.json" % (k + 1)),
                  encoding="utf-8") as src:
            msg = json.load(src)
        f.write(json.dumps({"op": "publish", "topic": "/obstacles_lethal", "msg": msg},
                           ensure_ascii=False, separators=(",", ":")) + "\n")
    f.write(json.dumps({"op": "publish", "topic": "/obstacles_blocked", "msg": pb},
                       ensure_ascii=False, separators=(",", ":")) + "\n")
    with open(os.path.join(OUT, "obstacles_lethal_empty.json"), encoding="utf-8") as src:
        f.write(json.dumps({"op": "publish", "topic": "/obstacles_lethal",
                            "msg": json.load(src)},
                           ensure_ascii=False, separators=(",", ":")) + "\n")


# ---------- 底图转 PNG，供 preview.html 内嵌 ----------
def write_png(path, w, h, gray_rows):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = bytearray()
    for row in gray_rows:
        raw.append(0)              # filter type 0
        raw += row
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return os.path.getsize(path)


rows = [raster[r * W:(r + 1) * W] for r in range(H)]   # PNG 与 PGM 同为自上而下
png_path = os.path.join(OUT, "16f01.png")
png_size = write_png(png_path, W, H, rows)

# ---------- 自检：层 A 的格子不能落在静态墙上（未知区的那簇除外） ----------
unknown_blob = set(disk(unknown_spot[0], unknown_spot[1], 0.15)) if unknown_spot else set()
for k in range(FRAMES):
    with open(os.path.join(OUT, "obstacles_lethal_%02d.json" % (k + 1)), encoding="utf-8") as f:
        m = json.load(f)
    gz = base64.b64decode(m["data"])
    raw = zlib.decompress(gz, 15 + 32)
    assert len(raw) == m["count"] * 4, "帧 %d 字节数与 count 不符" % k
    acc, cells_back = 0, []
    for j in range(0, len(raw), 4):
        acc += struct.unpack("<I", raw[j:j + 4])[0]
        cells_back.append(acc)
    assert cells_back == sorted(set(cells_back)), "帧 %d 解出的索引非严格升序" % k
    bad = [i for i in cells_back if cellkind[i] == WALL and i not in unknown_blob]
    assert not bad, "帧 %d 有 %d 个格子落在静态墙上" % (k, len(bad))
print("自检通过：5 帧层 A 往返解码一致、未压到静态墙")

# ---------- 参考实现 preview.html（内嵌底图与全部帧，双击即可打开） ----------
png_b64 = base64.b64encode(open(png_path, "rb").read()).decode("ascii")
frames_js = {}
for name in ["obstacles_lethal_%02d.json" % (k + 1) for k in range(FRAMES)] + \
            ["obstacles_lethal_empty.json", "obstacles_blocked.json",
             "obstacles_blocked_with_temp.json"]:
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        frames_js[name.replace(".json", "")] = json.load(f)

HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>障碍层 mock 数据预览</title>
<style>
  body{margin:0;background:#11161b;color:#dfe6ec;font:15px/1.7 -apple-system,"PingFang SC",sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px;display:flex;flex-direction:column;gap:20px}
  h1{font-size:22px;margin:0}
  .bar{display:flex;flex-wrap:wrap;gap:16px;align-items:center;background:#1a2229;
       border:1px solid #2a343d;border-radius:4px;padding:14px 16px}
  label{display:flex;gap:7px;align-items:center;cursor:pointer;user-select:none}
  button{background:#e0533d;color:#fff;border:0;border-radius:3px;padding:7px 16px;
         font-size:14px;cursor:pointer;font-family:inherit}
  button:disabled{opacity:.45;cursor:default}
  select{background:#242e36;color:#dfe6ec;border:1px solid #35424c;border-radius:3px;padding:6px 8px;font-family:inherit}
  canvas{background:#0b0f13;border:1px solid #2a343d;border-radius:4px;width:100%;height:auto;
         image-rendering:pixelated;display:block}
  .meta{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:13px;color:#8b9aa7;
        display:flex;flex-wrap:wrap;gap:22px}
  .meta b{color:#e0533d;font-weight:600}
  .meta i{color:#5bb8c9;font-style:normal;font-weight:600}
  pre{background:#1a2229;border:1px solid #2a343d;border-radius:4px;padding:16px;
      overflow-x:auto;font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.75;color:#c3ced8}
  .note{color:#8b9aa7;font-size:14px}
</style></head><body><div class="wrap">
<h1>障碍层 mock 数据预览</h1>
<p class="note">底图 16f01（547 × 611，每格 0.05 米）＋ 两层障碍数据。解码用的就是给前端的那段代码，没有额外依赖。</p>

<div class="bar">
  <label><input type="checkbox" id="showBase" checked> 底图</label>
  <label><input type="checkbox" id="showB"> 层 B（不可进入区）</label>
  <label><input type="checkbox" id="showA" checked> 层 A（临时障碍）</label>
  <select id="frameSel"></select>
  <select id="blockedSel">
    <option value="obstacles_blocked">层 B：只有墙</option>
    <option value="obstacles_blocked_with_temp">层 B：含临时障碍</option>
  </select>
  <button id="play">播放 5 帧</button>
</div>

<canvas id="cv" width="547" height="611"></canvas>

<div class="meta">
  <span>层 A 命中格 <b id="cntA">-</b></span>
  <span>层 B 命中格 <i id="cntB">-</i></span>
  <span>鼠标处世界坐标 <span id="pos">-</span></span>
</div>

<pre id="code"></pre>
</div>

<script>
const MAP_PNG = "data:image/png;base64,__PNG__";
const FRAMES = __FRAMES__;

async function decodeCells(msg) {
  if (msg.count === 0) return new Uint32Array(0);      // 空帧：清层
  const bin = Uint8Array.from(atob(msg.data), c => c.charCodeAt(0));
  const raw = new Uint8Array(await new Response(
    new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"))
  ).arrayBuffer());
  const dv = new DataView(raw.buffer);
  const cells = new Uint32Array(msg.count);
  let acc = 0;
  for (let i = 0; i < msg.count; i++) {
    acc += dv.getUint32(i * 4, true);                  // true = 小端
    cells[i] = acc;                                    // 前缀和还原绝对索引
  }
  return cells;
}
document.getElementById("code").textContent = decodeCells.toString();

const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
const img = new Image();
const cache = {};
let curA = "obstacles_lethal_01", curB = "obstacles_blocked";

async function cells(name) {
  if (!cache[name]) cache[name] = await decodeCells(FRAMES[name]);
  return cache[name];
}

function paint(list, msg, color) {
  const W = msg.region.width, H = msg.region.height;
  ctx.fillStyle = color;
  for (const i of list) {
    const col = i % W, row = Math.floor(i / W);
    ctx.fillRect(msg.region.col0 + col, H - 1 - (msg.region.row0 + row), 1, 1);
  }
}

async function draw() {
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (document.getElementById("showBase").checked) ctx.drawImage(img, 0, 0);
  if (document.getElementById("showB").checked) {
    const m = FRAMES[curB];
    paint(await cells(curB), m, "rgba(70,150,255,.45)");
    document.getElementById("cntB").textContent = m.count;
  } else document.getElementById("cntB").textContent = "-";
  if (document.getElementById("showA").checked) {
    const m = FRAMES[curA];
    paint(await cells(curA), m, "#e0533d");
    document.getElementById("cntA").textContent = m.count;
  } else document.getElementById("cntA").textContent = "-";
}

const sel = document.getElementById("frameSel");
for (const k of Object.keys(FRAMES).filter(k => k.startsWith("obstacles_lethal"))) {
  const o = document.createElement("option"); o.value = k; o.textContent = k; sel.appendChild(o);
}
sel.onchange = () => { curA = sel.value; draw(); };
["showBase", "showB", "showA"].forEach(id => document.getElementById(id).onchange = draw);
document.getElementById("blockedSel").onchange = (e) => { curB = e.target.value; draw(); };

document.getElementById("play").onclick = async (e) => {
  e.target.disabled = true;
  for (let k = 1; k <= 5; k++) {
    sel.value = curA = "obstacles_lethal_0" + k;
    await draw();
    await new Promise(r => setTimeout(r, 700));
  }
  e.target.disabled = false;
};

cv.onmousemove = (ev) => {
  const r = cv.getBoundingClientRect();
  const px = (ev.clientX - r.left) / r.width * cv.width;
  const py = (ev.clientY - r.top) / r.height * cv.height;
  const m = FRAMES[curA];
  const x = m.origin[0] + px * m.resolution;
  const y = m.origin[1] + (cv.height - py) * m.resolution;
  document.getElementById("pos").textContent = x.toFixed(2) + ", " + y.toFixed(2) + " 米";
};

img.onload = draw;
img.src = MAP_PNG;
</script></body></html>
"""
HTML = HTML.replace("__PNG__", png_b64).replace(
    "__FRAMES__", json.dumps(frames_js, ensure_ascii=False, separators=(",", ":")))
with open(os.path.join(OUT, "preview.html"), "w", encoding="utf-8") as f:
    f.write(HTML)
print("preview.html %d bytes" % os.path.getsize(os.path.join(OUT, "preview.html")))

print("map: %dx%d  res=%s  origin=%s" % (W, H, RESOLUTION, ORIGIN))
print("walls=%d  blocked_static=%d" % (len(walls), len(blocked_static_cells)))
print("spots=%s  unknown_spot=%s" % (spots, unknown_spot))
print("png=%d bytes" % png_size)
for name, (path, size), count in manifest:
    print("%-34s count=%-7d %6d bytes" % (name, count, size))
