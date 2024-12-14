'''
    2024-12-14
    TrackTrain v2
    动车组担当查询
    by TKP30
'''
import requests
import datetime
import mpaas
import time
import pymysql
from pathlib import Path
import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor, wait

UNIQUE = []
COMMITS = 0

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainTrack")
logger.setLevel(logging.DEBUG)

_fh = logging.FileHandler("cr-emu.log")
_fh.setLevel(logging.DEBUG)
logger.addHandler(_fh)

requests.packages.urllib3.disable_warnings()


# MySQL 数据库连接
def connect_mysql():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="123456",
        database="traintrack"
    )


def formatTime(offset=0):
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - datetime.timedelta(days=offset)).strftime('%Y%m%d')


def deformatTime(ts):
    return int(datetime.datetime.strptime(ts, "%Y%m%d%H%M").timestamp())


def fixTrainset(tsn):
    tsn = tsn.replace("CRH2C-1-", "CRH2C-")  # CRH2C一二代
    tsn = tsn.replace("CRH2C-2-", "CRH2C-")
    return tsn


def getTrainList(day=0):
    for key in ["D", "G", "C"]:
        for tn in range(1, 100):
            for x in range(5):
                try:
                    req = requests.get(
                        f"https://search.12306.cn/search/v1/h5/search?keyword={key+str(tn)}", verify=False)
                    jr = req.json()
                    cnt = 0
                    for car in jr["data"]:
                        if car["params"]["train_no"] in UNIQUE or car["type"] != "001":
                            continue
                        UNIQUE.append(car["params"]["train_no"])
                        cnt += 1
                        yield car["params"]["station_train_code"]
                    logger.info(f"{key}{tn} 号段搜索好，共 {cnt} 个车次")
                    time.sleep(0.1)
                    break
                except Exception as e:
                    logger.info(f"{key}{tn} 号段限速")
                    time.sleep(20)
                    continue


def findRunTrains(day=0):
    global UNIQUE, COMMITS
    conn = connect_mysql()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS RECORDS (
            day VARCHAR(10) NOT NULL,
            timestamp BIGINT NOT NULL,
            trainCodeA VARCHAR(50),
            trainCodeB VARCHAR(50),
            carA VARCHAR(50),
            carB VARCHAR(50)
        )
    """)
    conn.commit()
    logger.info("数据库初始化完成，启动主循环")
    today = datetime.datetime.today()
    new_date = today + datetime.timedelta(days=day)

    def parseTrainJL(i):
        global UNIQUE, COMMITS
        conn = connect_mysql()
        cursor = conn.cursor()
        codeFull = ""
        tsfirst = -1
        
        cursor.execute(
            "SELECT COUNT(*) FROM RECORDS WHERE trainCodeA=%s AND day=%s", (i, formatTime(-day)))
        if cursor.fetchone()[0] > 0:
            logger.info(f"车次 {i} 在 {new_date.strftime('%Y-%m-%d')} 已存在，移除数据")
            cursor.execute(
                "DELETE FROM RECORDS WHERE trainCodeA=%s AND day=%s", (i, formatTime(-day)))

        for x in range(5):
            try:
                r2 = requests.post("https://mobile.12306.cn/wxxcx/wechat/main/travelServiceQrcodeTrainInfo", data={
                    "trainCode": i,
                    "startDay": formatTime(-day)
                }, verify=False)
            except:
                continue
            try:
                codeFull = r2.json()[
                    "data"]["trainDetail"]["stationTrainCodeAll"]
                tsfirst = deformatTime(
                    formatTime(-day)+r2.json()["data"]["startTime"])
                break
            except:
                logger.info(f"车次 {i} 在 {new_date.strftime('%Y-%m-%d')} 不跑")
                return
        i = codeFull.split("/")
        for _ in range(3):
            try:
                d = mpaas.postM(
                    "homepage.getTrainInfoImg",
                    {
                        "startTrainDate": formatTime(-day),
                        "trainCode": i[0],
                        "trainSetName": ""
                    }
                )
                if d["isHaveData"] == "Y":
                    r = [fixTrainset(x["trainsetName"])
                         for x in d["trainInfo"]]
                    cursor.execute(
                        "INSERT INTO RECORDS (day, timestamp, trainCodeA, trainCodeB, carA, carB) VALUES (%s, %s, %s, %s, %s, %s)",
                        (formatTime(-day),
                         tsfirst,
                         i[0],
                         i[1] if len(i) > 1 else "",
                         r[0],
                         r[1] if len(r) > 1 else "")
                    )
                    logger.info(f"车次 {i[0]} 编组 {' + '.join(r)}")
                    conn.commit()
                    COMMITS += 1
                    time.sleep(0.25)
                    return
            except Exception as e:
                time.sleep(0.1)

        logger.info(f"车次 {i[0]} 无数据")

    with ThreadPoolExecutor(30) as tp:
        tp.map(parseTrainJL, getTrainList(day))
    logger.info(f"{new_date.strftime('%Y-%m-%d')} 爬取完成")

    if day == 0:
        cursor.execute("DELETE FROM RECORDS WHERE day < %s", (formatTime(60),))
        conn.commit()
        logger.info("清除完成60天前数据")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--day", help="爬取的日期（0为今天，5为未来第5天）", type=int, default=0)
    args = parser.parse_args()

    current_dir = Path(__file__).resolve().parent
    os.chdir(current_dir)

    if args.day < 0 or args.day > 10:
        print("ERROR: 超出可接受的数值范围")
        exit()

    logger.info("====CR-TRACKER====")
    logger.info(f"开始爬取：{args.day}天数据")
    findRunTrains(args.day)
