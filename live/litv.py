# -*- coding: utf-8 -*-
# @Author  : Doubebly
# @Time    : 2025/03/24 修正列表与音频
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
        if proxy:
            self.proxy01 = {"http": proxy, "https": proxy}
            self.is_proxy = True
        else:
            self.proxy01 = None
            self.is_proxy = False

        self.key = b'doubebly12345678'
        self.iv = b'doubebly12345678'

    def encrypt(self, text):
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        ct_bytes = cipher.encrypt(pad(text.encode('utf-8'), 16))
        return ct_bytes.hex()

    def decrypt(self, text):
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        pt = unpad(cipher.decrypt(bytes.fromhex(text)), 16)
        return pt.decode('utf-8')

    def homeContent(self, filter):
        result = {'class': [{"type_id": "live", "type_name": "LiTV直播"}]}
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        videos = []
        # 使用最新的频道列表入口
        url = "https://www.litv.tv/channel/list"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.litv.tv/"
        }
        try:
            rsp = requests.get(url, headers=headers, proxies=self.proxy01 if self.is_proxy else None, timeout=10)
            rsp.encoding = 'utf-8'
            # 兼容性修复：如果正则匹配不到，尝试提取页面中所有的 channel id
            # 现在的 LiTV 数据通常挂在类似 "allChannels" 的 JSON 结构里
            channel_data = re.findall(r'/channel/([^"/]+)">.*?<div class="title">([^<]+)</div>', rsp.text, re.S)
            if not channel_data:
                # 备用方案：抓取 JS 变量中的数据
                channel_data = re.findall(r'channelId":"([^"]+)","name":"([^"]+)"', rsp.text)

            for cid, name in channel_data:
                videos.append({
                    "vod_id": cid,
                    "vod_name": name,
                    "vod_pic": f"https://pic.litv.tv/v1/node/web/live/channel/{cid}/logo.png",
                    "vod_remarks": "直播"
                })
        except:
            pass
        
        result.update({'list': videos, 'page': 1, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)})
        return result

    def detailContent(self, array):
        tid = array[0]
        return {"list": [{"vod_id": tid, "vod_play_from": "LiTV", "vod_play_url": f"播放${tid}"}]}

    def playerContent(self, flag, id, vipFlags):
        # 动态获取该频道对应的具体 video_id 和 audio_id
        url = f"https://www.litv.tv/channel/{id}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            rsp = requests.get(url, headers=headers, proxies=self.proxy01 if self.is_proxy else None, timeout=10)
            # 核心：抓取你提到的 "2" 和 "9"
            v_match = re.search(r'video_id["\s:]+["\']?([^"\', ]+)["\']?', rsp.text)
            a_match = re.search(r'audio_id["\s:]+["\']?([^"\', ]+)["\']?', rsp.text)
            
            b = v_match.group(1) if v_match else "2"
            c = a_match.group(1) if a_match else "9"
            
            payload = f"{id},{b},{c}"
            proxy_url = f"{self.getProxyUrl()}&type=m3u8&url={self.encrypt(payload)}"
            return {"parse": 0, "playUrl": "", "url": proxy_url, "header": headers}
        except:
            return {"parse": 0, "url": ""}

    def getProxyUrl(self):
        return "/proxy?do=litv"

    def homeProxy(self, params):
        if params.get('type') == 'm3u8':
            try:
                content = self.decrypt(params['url'])
                a, b, c = content.split(",")
                # 时间戳偏移计算
                timestamp = int(time.time() / 4 - 355017625)
                t = timestamp * 4
                
                m3u8 = f'#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:{timestamp}\n'
                for i in range(10):
                    # 按照你抓包成功的 134000_zho 格式进行精确拼装
                    ts_url = f'https://ntd-tgc.cdn.hinet.net/live/pool/{a}/litv-pc/{a}-avc1_6000000={b}-mp4a_134000_zho={c}-begin={t}0000000-dur=40000000-seq={timestamp}.ts'
                    
                    # 关键：hex 加密确保 TS 链接在 M3U8 中不换行，解决 Manifest 报错
                    enc_ts = self.encrypt(ts_url)
                    m3u8 += f'#EXTINF:4.0,\n{self.getProxyUrl()}&type=ts&url={enc_ts}\n'
                    timestamp += 1
                    t += 4
                return [200, "application/vnd.apple.mpegurl", m3u8]
            except:
                return [500, "text/plain", "Error"]

        elif params.get('type') == 'ts':
            try:
                url = self.decrypt(params['url'])
                # 解决无声：必须补全 Referer 骗过 CDN
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.litv.tv/',
                    'Origin': 'https://www.litv.tv'
                }
                res = requests.get(url, headers=headers, proxies=self.proxy01 if self.is_proxy else None, timeout=15)
                # 状态码 200 + video/mp2t 是解决无声的最终方案
                return [200, "video/mp2t", res.content]
            except:
                return [404, "text/plain", "TS Error"]
