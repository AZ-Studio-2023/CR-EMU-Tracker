from flask import *
import sqlite3
import time

app = Flask("TrainTrack")

start_time = time.time()
visit_count = 0
query_count = 0

def detectType(kw):
    if kw.startswith("G") or kw.startswith("D"):
        return "train"
    elif kw.startswith("C"):
        try:
            if kw[1] == "R":
                return "car"
            return "train"
        except:
            return "train"
    else:
        return "invaild"


@app.route("/")
def index():
    global visit_count
    visit_count += 1
    return render_template("index.html")


@app.route("/faq")
def faqpage():
    global visit_count
    visit_count += 1
    return render_template("faq.html")

@app.route("/docs")
def docpage():
    global visit_count
    visit_count += 1
    return render_template("docs.html")


@app.route("/api/query")
def query():
    global query_count
    query_count+=1
    qn = request.values.get("keyword", None)
    if qn is None:
        return jsonify({
            "success": False,
            "data": []
        })

    d = sqlite3.connect("./records.db")
    s = None
    k = detectType(qn)
    if k == "train":
        s = d.cursor().execute(
            "SELECT * FROM RECORDS WHERE trainCodeA=? OR trainCodeB=? ORDER BY timestamp DESC LIMIT 50", (qn, qn))
    elif k == "car":
        s = d.cursor().execute(
            "SELECT * FROM RECORDS WHERE carA LIKE '%s%%' OR carB LIKE '%s%%' ORDER BY timestamp DESC LIMIT 50"%(qn, qn))
    else:
        return jsonify({
            "success": True,
            "data": []
        })
    d.commit()

    res = s.fetchall()

    if len(res) == 0:
        return jsonify({
            "success": True,
            "data": []
        })

    return jsonify({
        "success": True,
        "data": list(reversed(sorted([{
            "runDate": time.strftime('%Y-%m-%d %H:%M', time.localtime(x[1])),
            "trainNum": f"{x[2]}/{x[3]}" if x[3] != "" else x[2],
            "trainCode": f"{x[4]} + {x[5]}" if x[5] != "" else x[4]
        } for x in res], key=lambda a: time.mktime(time.strptime(a["runDate"], '%Y-%m-%d %H:%M')))))
    })

@app.route("/api/stats")
def get_stats():
    uptime = time.time() - start_time
    days = int(uptime // (24 * 3600))
    hours = int((uptime % (24 * 3600)) // 3600)
    return jsonify({
        "days": days,
        "hours": hours,
        "visits": visit_count,
        "queries": query_count
    })

if __name__ == "__main__":
    app.run("0.0.0.0", 80, debug=True)
