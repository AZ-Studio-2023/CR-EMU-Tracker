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
from pymongo import MongoClient
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

# MongoDB连接
client = MongoClient('mongodb://localhost:27017/')
db = client['traintrack']
collection = db.records

def format_time(offset=0):
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - 
            datetime.timedelta(days=offset)).strftime('%Y%m%d')

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
                f"https://mobile.12306.cn/weixin/wxcore/queryTrain?ticket_no={key}&depart_date={format_time()}", 
                verify=False
            )
            for car in req.json()["data"]:
                PBAR.total += 1
                yield car["ticket_no"]
        except Exception as e:
            continue

def parse_train_jl(train_code):
    global UNIQUE, COMMITS, PBAR
    date = datetime.datetime.utcnow() + datetime.timedelta(hours=8) + datetime.timedelta(days=DAY)

    # 检查并删除已存在记录
    collection.delete_many({
        "trainCodeA": train_code,
        "day": date.strftime('%Y%m%d')
    })

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
            collection.insert_one({
                "day": date.strftime('%Y%m%d'),
                "timestamp": tsfirst,
                "trainCodeA": list(i)[0],
                "trainCodeB": list(i)[1] if len(i) > 1 else "",
                "carA": r[0],
                "carB": r[1] if len(r) > 1 else ""
            })
            logger.info(f"车次 {train_code} 编组 {'+'.join(r)}")
            COMMITS += 1
            PBAR.update()
            time.sleep(0.05)
            if RECHECK:
                table_data = collection.find({ "day": date.strftime('%Y%m%d'), "timestamp": tsfirst, "trainCodeA": list(i)[0], "trainCodeB": list(i)[1] if len(i) > 1 else ""})
                if table_data :
                    if table_data[0]["carA"] != r[0] or table_data[0]["carB"] != r[1] if len(r) > 1 else "":
                        logger.warning(f"车次 {train_code} 数据库数据不符，重新插入")
                        collection.delete_one(table_data[0])
                        collection.insert_one({
                            "day": date.strftime('%Y%m%d'),
                            "timestamp": tsfirst,
                            "trainCodeA": list(i)[0],
                            "trainCodeB": list(i)[1] if len(i) > 1 else "",
                            "carA": r[0],
                            "carB": r[1] if len(r) > 1 else ""
                        })

                        
    except Exception as e:
        logger.warning(f"车次 {train_code} 无法写入数据库: {e}")
        time.sleep(0.1)

def find_run_trains(day=0):
    global UNIQUE, COMMITS, DAY, PBAR
    DAY = day
    PBAR = tqdm.tqdm(total=0, desc="遍历车次", unit="组",
                     position=0, file=sys.stdout)

    # 确保索引存在
    collection.create_index([("day", 1)])
    collection.create_index([("trainCodeA", 1)])
    collection.create_index([("trainCodeB", 1)])
    collection.create_index([("carA", 1)])
    collection.create_index([("carB", 1)])
    
    logger.info("数据库初始化完成，启动主循环")

    with ThreadPoolExecutor(30) as executor:
        with tqdl.wrap_logging_for_tqdm(PBAR, logger=logger):
            executor.map(parse_train_jl, get_train_list(day))

    PBAR.close()

    logger.info(f"{format_time(-day)} 爬取完成")
    logger.info(f"提交了 {COMMITS} 行记录")

    if day == 0:
        # 删除60天前的数据
        collection.delete_many({"day": {"$lt": format_time(60)}})
        logger.info("清除完成60天前数据")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--day", help="爬取的日期（如0为今天，5为未来第5天，-2为前天）", type=int, default=0)
    parser.add_argument(
        "-r", "--recheck", help="提交数据到数据库时再次请求核对", action='store_true')
    args = parser.parse_args()
    RECHECK = args.recheck
    current_dir = Path(__file__).resolve().parent
    os.chdir(current_dir)

    if args.day < -5 or args.day > 14:
        logger.error("ERROR: 超出可接受的数值范围")
        exit()

    logger.info("====CR-TRACKER====")
    logger.info(f"开始爬取：{args.day}天数据")
    find_run_trains(args.day)