# slate のレイアウト（GUI の JSON）から、GP2040-CE のファームウェア（uf2）を作る（2026-10-10）。
# build_firmware.py --layout と同じ割当・同じ設定を、ブラウザの Pyodide でも動くように書いたもの。
#  ・GPIO の割当：主ボタンは x 昇順（同 x は y の小さい順）で GP2 から。機能は名前ごとの既定か JSON の func。制御ボタンは gp と func（無ければ label から）。
#  ・設定は GP2040-CE の Config（protobuf。fw/config_pb2.py は公式の .proto から生成したもの）。
#  ・uf2 は Microsoft の UF2 形式（512 バイトのブロック。先頭 32 バイトの頭・256 バイトの中身・詰め物・末尾の印）。公式の uf2 を 2MB のフラッシュの像に戻し、
#    末尾 32KB の利用者設定の領域（0x1F8000〜）に、直列化した設定＋足（大きさ 4 バイト・CRC32 4 バイト・印 4 バイト）を右詰めで置き、uf2 に戻す。
#  ・正しさは、build_firmware.py --layout の出力と SHA256 が一致することで確かめる（verify_fw.py）。
import struct, binascii, sys, os
DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.join(DIR, "fw") not in sys.path: sys.path.insert(0, os.path.join(DIR, "fw"))
import config_pb2 as pb2

A = dict(NONE=-10, UP=1, DOWN=2, LEFT=3, RIGHT=4, B1=5, B2=6, B3=7, B4=8, L1=9, R1=10, L2=11, R2=12, S1=13, S2=14, A1=15, A2=16, L3=17, R3=18)
DEFAULT_FUNC = {"L": "LEFT", "D": "DOWN", "R": "RIGHT", "Up": "UP", "c1t": "B1", "c1b": "B3", "c2t": "B2", "c2b": "B4", "c3t": "R2", "c3b": "R1", "c4t": "L2", "c4b": "L1", "thumb": "L3", "palm": "L3"}
CTRL_FUNC = {"A2": "A2", "A1": "A1", "ST": "S2", "SEL": "S1"}
NUM_GPIO = 30; INPUT_MODE_XINPUT = 0; INPUT_MODE_SWITCH = 1
UF2_MAGIC_FIRST = 0x0A324655; UF2_MAGIC_SECOND = 0x9E5D5157; UF2_MAGIC_FINAL = 0x0AB16F30; UF2_FAMILY_RP2040 = 0xE48BFF56
FLASH_BASE = 0x10000000; STORAGE_SIZE = 32768; USER_CONFIG_OFFSET = 2 * 1024 * 1024 - STORAGE_SIZE; FOOTER_MAGIC = b"\x65\xe3\xf1\xd2"

def gpio_actions(layout):
    """レイアウトから GPIO → 機能の番号。build_firmware.py --layout と同じ規則。"""
    B = layout["buttons"]; near = sorted(B, key=lambda n: (B[n]["x"], B[n]["y"]))
    if len(near) > 14: raise ValueError("主ボタンは 14 個まで（GP2〜15）")
    out = {}
    for i, n in enumerate(near):
        f = B[n].get("func", DEFAULT_FUNC.get(n))
        if f not in A: raise ValueError("ボタン %s の機能 %r が不明" % (n, f))
        out[2 + i] = A[f]
    ctrl = layout.get("ctrl") or [{"gp": 21, "label": "A2"}, {"gp": 20, "label": "A1"}, {"gp": 19, "label": "ST"}, {"gp": 18, "label": "SEL"}]
    for e in ctrl:
        f = e.get("func", CTRL_FUNC.get(e.get("label")))
        if f not in A: raise ValueError("制御ボタン %r の機能が不明" % e)
        out[int(e["gp"])] = A[f]
    return out

def build_config(actions, input_mode):
    config = pb2.Config()
    config.gamepadOptions.inputMode = input_mode
    for gpio in range(NUM_GPIO):
        info = config.gpioMappings.pins.add(); info.action = actions.get(gpio, A["NONE"]); info.direction = 0
    config.gpioMappings.profileLabel = "Conductive HB"
    config.migrations.gpioMappingsMigrated = True
    return config

def config_section(config):
    """直列化した設定に足（大きさ・CRC32・印。いずれもリトルエンディアン）を付け、32KB の領域の末尾に右詰めで置く。"""
    body = config.SerializeToString()
    blob = body + struct.pack("<I", len(body)) + struct.pack("<I", binascii.crc32(body) & 0xFFFFFFFF) + FOOTER_MAGIC
    if len(blob) > STORAGE_SIZE: raise ValueError("設定が 32KB を超えた")
    return bytes(STORAGE_SIZE - len(blob)) + blob

def uf2_to_image(uf2):
    """uf2 をフラッシュの像（先頭からの連続したバイト列）に戻す。ブロックの飛びは 0 で埋める。"""
    if len(uf2) % 512: raise ValueError("uf2 の長さが 512 の倍数でない")
    img = bytearray(); last_end = None
    for i in range(0, len(uf2), 512):
        m1, m2, flags, addr, nbytes, blk, nblk, fam = struct.unpack("<8I", uf2[i:i + 32])
        if m1 != UF2_MAGIC_FIRST or m2 != UF2_MAGIC_SECOND: raise ValueError("uf2 の印が違う")
        if last_end is not None:
            if addr < last_end: raise ValueError("uf2 のアドレスが戻っている")
            img += bytes(addr - last_end)
        img += uf2[i + 32:i + 32 + nbytes]; last_end = addr + nbytes
    return img

def image_to_uf2(parts):
    """[(先頭からのオフセット, bytes), ...] を uf2 にする（256 バイトずつ・RP2040 の family ID）。"""
    chunks = []
    for off, data in parts:
        for j in range(0, len(data), 256): chunks.append((FLASH_BASE + off + j, bytes(data[j:j + 256])))
    out = bytearray()
    for k, (addr, data) in enumerate(chunks):
        out += struct.pack("<8I", UF2_MAGIC_FIRST, UF2_MAGIC_SECOND, 0x2000, addr, 256, k, len(chunks), UF2_FAMILY_RP2040)
        out += data + bytes(476 - len(data)) + struct.pack("<I", UF2_MAGIC_FINAL)
    return bytes(out)

def build_uf2(layout, firmware_uf2, input_mode=INPUT_MODE_XINPUT):
    """公式の uf2（bytes）と レイアウトから、割当を焼き込んだ uf2（bytes）を返す。"""
    actions = gpio_actions(layout)
    img = uf2_to_image(firmware_uf2)
    return image_to_uf2([(0, img), (USER_CONFIG_OFFSET, config_section(build_config(actions, input_mode)))]), actions

def verify_uf2(uf2, actions, input_mode):
    """作った uf2 から設定を読み戻し、割当とモードが一致するかを確かめる。"""
    img = uf2_to_image(uf2); sect = img[USER_CONFIG_OFFSET:USER_CONFIG_OFFSET + STORAGE_SIZE]
    if sect[-4:] != FOOTER_MAGIC: return False, "足の印が無い"
    size = struct.unpack("<I", sect[-12:-8])[0]; crc = struct.unpack("<I", sect[-8:-4])[0]; body = sect[-12 - size:-12]
    if binascii.crc32(body) & 0xFFFFFFFF != crc: return False, "CRC が合わない"
    cfg = pb2.Config(); cfg.ParseFromString(bytes(body))   # 古い protobuf は bytearray を受け付けない
    if cfg.gamepadOptions.inputMode != input_mode: return False, "入力モードが違う"
    for gpio, act in actions.items():
        if cfg.gpioMappings.pins[gpio].action != act: return False, "GP%d の割当が違う" % gpio
    return True, "一致"

def build_uf2_json(layout_json, firmware_path, input_mode=0):
    """Pyodide 向け：JSON の文字列とファイルの経路を受け取り、uf2 を書いた経路と割当の説明を JSON で返す。"""
    import json
    layout = json.loads(layout_json); fw = open(firmware_path, "rb").read()
    uf2, actions = build_uf2(layout, fw, input_mode)
    ok, msg = verify_uf2(uf2, actions, input_mode)
    out = "/tmp/out.uf2"; open(out, "wb").write(uf2)
    inv = {v: k for k, v in A.items()}
    B = layout["buttons"]; near = sorted(B, key=lambda n: (B[n]["x"], B[n]["y"]))
    LAB = {"L": "L", "D": "D", "R": "R", "Up": "UP", "c1t": "LK", "c1b": "LP", "c2t": "MK", "c2b": "MP", "c3t": "HK", "c3b": "HP", "c4t": "KK", "c4b": "PP", "thumb": "THU", "palm": "PALM"}
    table = [{"gp": g, "func": inv[a], "label": (B[near[g - 2]].get("label", LAB.get(near[g - 2], near[g - 2])) if 2 <= g <= 15 else "制御")} for g, a in sorted(actions.items())]
    return json.dumps({"path": out, "size": len(uf2), "verified": ok, "message": msg, "table": table}, ensure_ascii=False)

if __name__ == "__main__":
    import json, hashlib
    layout = json.load(open(sys.argv[1])); fw = open(sys.argv[2] if len(sys.argv) > 2 else os.path.join(DIR, "fw", "GP2040-CE_0.7.12_Pico.uf2"), "rb").read()
    for mode, name in ((INPUT_MODE_XINPUT, "XInput"), (INPUT_MODE_SWITCH, "Switch")):
        uf2, actions = build_uf2(layout, fw, mode); ok, msg = verify_uf2(uf2, actions, mode)
        print("%s：%d バイト・読み戻し %s・SHA256 %s" % (name, len(uf2), msg, hashlib.sha256(uf2).hexdigest()))
