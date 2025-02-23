from mpaas import postM
import pymysql
import datetime
import unittest

class VerifyDBTest(unittest.TestCase):
    def test_random(self):
        print("[TEST] 抽样测试开始")

        c = pymysql.connect(host="localhost",user="root",password="123456",database="traintrack")
        u = c.cursor()
        u.execute("SELECT * FROM RECORDS WHERE day=%s ORDER BY RAND() LIMIT 30;", ((datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y%m%d')))
        # 取当天抽30
        r = u.fetchall()

        for x in list(r):
            tn = x[2]
            print("[TEST] 抽样 %s 次"%tn)
            m = postM("homepage.getTrainInfoImg",
                            {
                                "trainCode": tn,
                                "trainSetName": "",
                                "startTrainDate": (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y%m%d')
                            }
                            )
            
            ta = m["trainInfo"][0]["trainsetName"].replace("CRH2C-2","CRH2C").replace("CRH2C-1","CRH2C")
            print("[TEST] 复检A组车 %s"%ta)
            self.assertEqual(ta, x[4])

if __name__ == "__main__":
    unittest.main()