# Copied from railgo-parser
import requests
import json
import hashlib
import time
import urllib.parse
import gzip
import struct
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

#from railgo.config import *

class MpaaSCrypt(object):
    '''MpaaS加解密'''

    def serializeBuffer(self, g, edata):
        '''组包'''
        return bytes.fromhex(
            "02" +
            "{:06x}".format(len(g)) +
            g.hex() +
            "0f" +
            "{:06x}".format(len(edata)) +
            edata.hex()
        )

    def encrypt(self, buffer):
        '''加密'''
        #LOGGER.debug(buffer)
        buffer = gzip.compress(buffer.encode())
        ecp = AES.new(b'}\x00#\x15\xb7QQM\xdfK\xce\xc2\xbd\x15\xeeE', AES.MODE_CBC, b'F\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f')
        epp = pad(buffer, 16)
        return ecp.encrypt(epp)

    def decrypt(self, buffer):
        '''解密'''
        ecd = AES.new(b'}\x00#\x15\xb7QQM\xdfK\xce\xc2\xbd\x15\xeeE', AES.MODE_CBC, b'F\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f\x0f')
        return gzip.decompress(unpad(ecd.decrypt(buffer), 16)).decode()

class MpaaSClient(object):
    '''12306 MpaaS客户端'''
    cryptor = MpaaSCrypt()

    def __init__(self):
        super().__init__()

    def postForm(self, api, form):
        ts = time.strftime("%Y%m%d%H%M%S")
        form["baseDTO"] = {
            # "check_code": "14c9047c8bbe6d89b2ea27dc09d8e8b3",
            "check_code": self.__checkCode(ts),
            "device_no": "TEMP-ZtHkH8JaHw4DACg6y/l2Wykr",
            "h5_app_id": "60000013",
            "h5_app_version": "5.8.2.23",
            "hwv": "BNE-AL00",
            "mobile_no": "",
            "os_type": "a",
            "time_str": ts,
            "user_name": "",
            "version_no": "5.8.2.13"
        }
        buff = self.cryptor.encrypt(json.dumps([{
            "_requestBody": form
        }]))
        r = requests.post(
            "https://mobile.12306.cn/otsmobile/app/mgs/mgw.htm",
            data=self.cryptor.serializeBuffer(b'\x02\xf0\x1bCM\xb9\xd2%\xfb\x95\x02D^\xbf-\x93\x11\xe8\xb2\xd5\x83zU{?\x10H\x98i\x85\x84\x04\x1e', buff),
            headers={
                "pagets": "",
                "nbappid": "60000013",
                "nbversion": "5.8.2.23",
                "appv": "5.8.2.13",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 12; BNE-AL00 Build/V417IR)",
                "Platform": "ANDROID",
                "AppId": "9101430221728",
                "WorkspaceId": "product",
                "Version": "2",
                "Operation-Type": api,
                "x-app-sys-Id": "com.MobileTicket",
                "Retryable2": "0",
                "x-mgs-encryption": "1",
                "x-Content-Encoding": "mgss",
                "Content-Type": "application/json",
            })
        if r.content == b'':
            raise ConnectionError(
                "mPaaS Request Failed: "+r.headers["Result-Status"]+" "+urllib.parse.unquote(r.headers["Memo"]))
        return self.cryptor.decrypt(r.content)

    def __checkCode(self, ts):
        return hashlib.md5(b"F"+ts.encode()+b"TEMP-ZtHkH8JaHw4DACg6y/l2Wykr").hexdigest()

