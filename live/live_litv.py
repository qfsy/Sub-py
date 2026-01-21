# -*- coding: utf-8 -*-
# @Author  : Doubebly
# @Time    : 2025/3/23 21:55
import sys
import time
import json
import requests
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "Litv"

    def init(self, extend):
        self.extend = extend
        try:
            self.extendDict = json.loads(extend)
        except:
            self.extendDict = {}

        proxy = self.extendDict.get('proxy', None)
        if proxy is None:
            self.is_proxy = False
            self.proxy01 = None
        else:
            self.proxy01 = {'http': proxy, 'https': proxy}
            self.is_proxy = True

        # AES 配置保持一致
        self.key = b'doubebly12345678'
        self.iv = b'doubebly12345678'

    def encrypt(self, text):
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        ct_bytes = cipher.encrypt(pad(text.encode('utf-8'), 16))
        # 修复关键点 1：使用 hex 避免 base64 产生换行符破坏 M3U8 结构
        return ct_bytes.hex()

    def decrypt(self, text):
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        pt = unpad(cipher.decrypt(bytes.fromhex(text)), 16)
        return pt.decode('utf-8')

    def homeContent(self, filter):
        result = {}
        cateList = [{"type_id": "live", "type_name": "LiTV直播"}]
        result['class'] = cateList
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        videos = []
        # 抓取 LiTV 直播列表页
        url = "https://www.litv.tv/live/list"
        header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            rsp = requests.get(url, headers=header, proxies=self.proxy01 if self.is_proxy else None, timeout=10)
            # 提取页面中的频道信息
            matches = re.findall(r'href="/live/channel/([^"]+)">.*?alt="([^"]+)"', rsp.text)
            for match in matches:
                cid, name = match
                videos.append({
                    "vod_id": cid,
                    "vod_name": name,
                    "vod_pic": f"https://pic.litv.tv/v1/node/web/live/channel/{cid}/logo.png",
                    "vod_remarks": "直播"
                })
        except:
            pass
        result['list'] = videos
        result['page'] = 1
        result['pagecount'] = 1
        result['limit'] = len(videos)
        result['total'] = len(videos)
        return result

    def detailContent(self, array):
        tid = array[0]
        video = {
            "vod_id": tid,
            "vod_play_from": "LiTV",
            "vod_play_url": f"立即播放${tid}"
        }
        return {"list": [video]}

    def playerContent(self, flag, id, vipFlags):
        # 获取频道详情页，解析出 a, b, c 三个关键参数
        url = f"https://www.litv.tv/live/channel/{id}"
        header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            rsp = requests.get(url, headers=header, proxies=self.proxy01 if self.is_proxy else None, timeout=10)
            # 这里对应你原脚本解析 a,b,c 的逻辑（LiTV 这种拼凑流的核心）
            a = id
            b_match = re.search(r'video_id":\s*"([^"]+)"', rsp.text)
            c_match = re.search(r'audio_id":\s*"([^"]+)"', rsp.text)
            b = b_match.group(1) if b_match else "6000000"
            c = c_match.group(1) if c_match else "128000"
            
            payload = f"{a},{b},{c}"
            proxy_url = f"{self.getProxyUrl()}&type=m3u8&url={self.encrypt(payload)}"
            return {"parse": 0, "playUrl": "", "url": proxy_url, "header": header}
        except:
            return {"parse": 0, "url": ""}

    def getProxyUrl(self):
        return "/proxy?do=litv"

    def homeProxy(self, params):
        if params['type'] == 'm3u8':
            try:
                content = self.decrypt(params['url'])
                a, b, c = content.split(",")
                timestamp = int(time.time() / 4 - 355017625)
                t = timestamp * 4
                
                m3u8_text = f'#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:{timestamp}\n'
                for i in range(10):
                    # 修复关键点 2：更新音频码率标识为 128000_zho (或根据抓包微调)
                    ts_raw_url = f'https://ntd-tgc.cdn.hinet.net/live/pool/{a}/litv-pc/{a}-avc1_4000000={b}-mp4a_128000_zho={c}-begin={t}0000000-dur=40000000-seq={timestamp}.ts'
                    
                    enc_ts = self.encrypt(ts_raw_url)
                    ts_proxy = f'{self.getProxyUrl()}&type=ts&url={enc_ts}'
                    
                    m3u8_text += f'#EXTINF:4.0,\n{ts_proxy}\n'
                    timestamp += 1
                    t += 4
                return [200, "application/vnd.apple.mpegurl", m3u8_text]
            except Exception as e:
                return [500, "text/plain", str(e)]

        elif params['type'] == 'ts':
            try:
                url = self.decrypt(params['url'])
                # 修复关键点 3：补齐 Referer，否则 CDN 可能截断音频流
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.litv.tv/',
                    'Origin': 'https://www.litv.tv'
                }
                res = requests.get(url, headers=headers, proxies=self.proxy01 if self.is_proxy else None, timeout=15)
                # 修复关键点 4：状态码 200 + 正确 MIME 解决“有画无声”
                return [200, "video/mp2t", res.content]
            except:
                return [404, "text/plain", "Error"]