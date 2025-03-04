'''
    2024-12-14
    TrackTrain v2
    动车组担当查询
    by TKP30
'''
import requests
import datetime
import time
import sys
import pymysql
from dbutils.pooled_db import PooledDB
from pathlib import Path
import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from mpaas import postM
import tqdm
import tqdm_logging_wrapper as tqdl

# 全局变量
UNIQUE = set()
COMMITS = 0
DAY = 0
PBAR = None

# 日志配置
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainTrack")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("cr-emu.log")
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

requests.packages.urllib3.disable_warnings()

# 数据库连接池
pool = PooledDB(
    creator=pymysql,
    maxconnections=10,
    mincached=2,
    blocking=True,
    host="localhost",
    user="root",
    password="123456",
    database="traintrack"
)

# 获取数据库连接


def get_db_connection():
    return pool.connection()

# 时间格式化工具


def format_time(offset=0):
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - datetime.timedelta(days=offset)).strftime('%Y%m%d')


def deformat_time(ts):
    return int(datetime.datetime.strptime(ts, "%Y%m%d%H%M").timestamp())


def fix_trainset(tsn):
    tsn = tsn.replace("CRH2C-1-", "CRH2C-")  # CRH2C一二代
    tsn = tsn.replace("CRH2C-2-", "CRH2C-")
    return tsn


def get_train_list(day=0):
    global PBAR
    for key in ["D", "G", "C"]:
        try:
            req = requests.get(
                f"https://mobile.12306.cn/weixin/wxcore/queryTrain?ticket_no={key}&depart_date={format_time()}", verify=False)
            for car in req.json()["data"]:
                PBAR.total += 1
                yield car["ticket_no"]
        except Exception as e:
            continue


def parse_train_jl(train_code):
    global UNIQUE, COMMITS, PBAR
    conn = get_db_connection()
    cursor = conn.cursor()
    date = datetime.datetime.utcnow() + datetime.timedelta(hours=8) + datetime.timedelta(days=DAY)

    cursor.execute(
        "SELECT COUNT(*) FROM RECORDS WHERE trainCodeA=%s AND day=%s", (train_code, date.strftime('%Y%m%d')))
    if cursor.fetchone()[0] > 0:
        logger.info(f"车次 {train_code} 在 {date.strftime('%Y-%m-%d')} 已存在，移除数据")
        cursor.execute(
            "DELETE FROM RECORDS WHERE trainCodeA=%s AND day=%s", (train_code, date.strftime('%Y%m%d')))
        conn.commit()

    try:
        r2 = postM("trainTimeTable.queryTrainAllInfo", {
            "fromStation": "",
            "toStation": "",
            "trainCode": train_code,
            "trainType": "",
            "trainDate": date.strftime('%Y%m%d')
        })
        crj = json.loads(r2["trainData"])
        tsfirst = deformat_time(
            date.strftime('%Y%m%d') + r2["train"]["start_time"])
        i = {x["stationTrainCode"]
             for x in crj["stopTime"] if "stationTrainCode" in x}
        i.add(train_code)
    except Exception as e:
        logger.info(f"车次 {train_code} 当天不开行")
        PBAR.update()
        return

    if not i:
        logger.info(f"车次 {train_code} 无停靠数据")
        PBAR.update()
        return
    
    try:
        d = postM("homepage.getTrainInfoImg", {
            "startTrainDate": date.strftime('%Y%m%d'),
            "trainCode": list(i)[0],
            "trainSetName": ""
        })
        if d["isHaveData"] == "Y":
            r = [fix_trainset(x["trainsetName"]) for x in d["trainInfo"]]
            cursor.execute(
                "INSERT INTO RECORDS (day, timestamp, trainCodeA, trainCodeB, carA, carB) VALUES (%s, %s, %s, %s, %s, %s)",
                (date.strftime('%Y%m%d'), tsfirst, list(i)
                 [0], list(i)[1] if len(i) > 1 else "", r[0], r[1] if len(r) > 1 else "")
            )
            conn.commit()
            conn.close()
            logger.info(f"车次 {train_code} 编组 {'+'.join(r)}")
            COMMITS += 1
            PBAR.update()
            time.sleep(0.05)
    except Exception as e:
        logger.warning(f"车次 {train_code} 无法写入数据库: {e}")
        time.sleep(0.1)


def find_run_trains(day=0):
    global UNIQUE, COMMITS, DAY, PBAR
    conn = get_db_connection()
    DAY = day
    PBAR = tqdm.tqdm(total=0, desc="遍历车次", unit="组",
                     position=0, file=sys.stdout)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS RECORDS (
            day DATE NOT NULL,
            timestamp BIGINT NOT NULL,
            trainCodeA VARCHAR(50),
            trainCodeB VARCHAR(50),
            carA VARCHAR(50),
            carB VARCHAR(50)
        )""")
    conn.commit()
    logger.info("数据库初始化完成，启动主循环")

    with ThreadPoolExecutor(30) as executor:
        with tqdl.wrap_logging_for_tqdm(PBAR, logger=logger):
            executor.map(parse_train_jl, get_train_list(day))

    PBAR.close()

    logger.info(f"{format_time(-day)} 爬取完成")
    logger.info(f"提交了 {COMMITS} 行记录")

    if day == 0:
        cursor.execute("DELETE FROM RECORDS WHERE day < %s",
                       (format_time(60),))
        conn.commit()
        logger.info("清除完成60天前数据")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--day", help="爬取的日期（如0为今天，5为未来第5天，-2为前天）", type=int, default=0)
    args = parser.parse_args()

    current_dir = Path(__file__).resolve().parent
    os.chdir(current_dir)

    if args.day < -5 or args.day > 14:
        logger.error("ERROR: 超出可接受的数值范围")
        exit()

    logger.info("====CR-TRACKER====")
    logger.info(f"开始爬取：{args.day}天数据")
    find_run_trains(args.day)
