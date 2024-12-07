import asyncio
import aiohttp
import aiomysql
import logging
import mpaas
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import os

UNIQUE = []
commits = 0

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainTrack")
logger.setLevel(logging.DEBUG)

_fh = logging.FileHandler("cr-emu.log")
_fh.setLevel(logging.DEBUG)
logger.addHandler(_fh)

mysql_pool = None


def formatTime(offset=0):
    return (datetime.utcnow() + timedelta(hours=8) - timedelta(days=offset)).strftime('%Y%m%d')


def deformatTime(ts):
    return int(datetime.strptime(ts, "%Y%m%d%H%M").timestamp())


def fixTrainset(tsn):
    tsn = tsn.replace("CRH2C-1-", "CRH2C-")  # CRH2C一二代
    tsn = tsn.replace("CRH2C-2-", "CRH2C-")
    return tsn


async def init_mysql_pool():
    global mysql_pool
    mysql_pool = await aiomysql.create_pool(
        host="localhost",
        user="root",
        password="123456",
        db="traintrack",
        minsize=1,
        maxsize=30,
    )


async def getTrainList(client, day=0):
    global UNIQUE
    for key in ["D", "G", "C"]:
        for tn in range(1, 100):
            for x in range(5):
                try:
                    async with client.get(
                        f"https://search.12306.cn/search/v1/h5/search?keyword={key+str(tn)}",
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
                        }
                    ) as req:
                        jr = await req.json()
                        for car in jr["data"]:
                            if car["params"]["train_no"] in UNIQUE or car["type"] != "001":
                                continue
                            yield car["params"]["station_train_code"]
                            UNIQUE.append(car["params"]["train_no"])
                        logger.info(f"{key}{tn} 号段搜索好，共{len(jr['data'])}个车次")
                        await asyncio.sleep(0.25)
                    break
                except Exception as e:
                    logger.info(f"{key}{tn} 号段限速: {str(e)}")
                    await asyncio.sleep(20)
                    continue


async def parseTrainJL(client, i, day=0):
    global UNIQUE, commits
    try:
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                codeFull = ""
                tsfirst = -1

                # 检查是否已存在记录
                await cursor.execute(
                    "SELECT * FROM RECORDS WHERE day=%s AND (trainCodeA=%s OR trainCodeB=%s)",
                    (formatTime(-day), i, i)
                )
                if len(await cursor.fetchall()) > 0 and day != 0:
                    return  # 重复车次

                # 查询列车粗略信息（复车次，开行情况）
                try:
                    inf = await mpaas.postM(
                        client,
                        "trainTimeTable.queryTrainAllInfo",
                        {
                            "fromStation": "",
                            "toStation": "",
                            "trainCode": i,
                            "trainType": "",
                            "trainDate": formatTime(-day)
                        }
                    )

                    if inf["succ_flag"] == "0":
                        logger.info(f"车次{i} 今天不跑")
                        return
                    try:
                        ti = json.loads(inf["trainData"])
                    except:
                        # 列车运行图调整
                        logger.info(f"车次{i} 今天不跑")
                        return
                    
                    tns = set()
                    tns.add(i)
                    for x in ti["stopTime"]:
                        try:
                            tns.add(x["dispTrainCode"])
                        except:
                            pass
                    i = list(tns)
                except Exception as e:
                    logger.exception(e)

                try:
                    d = await mpaas.postM(
                        client,
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
                        await cursor.execute(
                            """
                            INSERT INTO RECORDS (day, timestamp, trainCodeA, trainCodeB, carA, carB)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (formatTime(-day),
                             tsfirst,
                             i[0],
                             i[1] if len(i) > 1 else "",
                             r[0],
                             r[1] if len(r) > 1 else "")
                        )
                        logger.info(f"车次{i[0]} 编组{' + '.join(r)}")
                        await conn.commit()
                        commits += 1
                except Exception as e:
                    logger.exception(e)
    except Exception as e:
        logger.exception(e)


async def findRunTrains(client, day=0):
    global UNIQUE, commits
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS RECORDS (
                    day VARCHAR(10) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    trainCodeA VARCHAR(50),
                    trainCodeB VARCHAR(50),
                    carA VARCHAR(50),
                    carB VARCHAR(50)
                )
            """)
            await conn.commit()
            logger.info("数据库初始化完成，开始爬取数据")

    ta = time.time()
    tasks = []
    async for train_code in getTrainList(client, day):
        tasks.append(parseTrainJL(client, train_code, day))
    await asyncio.gather(*tasks)

    logger.info(f"爬取完成 耗时{time.time()-ta}s 提交{commits}条记录")

    if day == 0:
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("DELETE FROM RECORDS WHERE day < %s", (formatTime(60),))
                await conn.commit()
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
    logger.info(f"开始爬取：第{args.day}天数据")

    async def main():
        await init_mysql_pool()
        async with aiohttp.ClientSession() as client:
            await findRunTrains(client, args.day)
        mysql_pool.close()
        await mysql_pool.wait_closed()

    asyncio.run(main())
    logger.info("完成")
