from flask import *
import datetime
import time
from pymongo import MongoClient
from bson.json_util import dumps
import os
import threading
from flask import send_from_directory

app = Flask("TrainTrack")

start_time = time.time()
visit_count = 0
query_count = 0

# SEO优化 - SITEMAP
BASE_URL = "https://example.com" 
SITEMAP_FILE = "sitemap.xml"
SITEMAP_KEY = "123456" 
SITEMAP_FOLDER = "sitemaps"  

# MongoDB连接
def connect_mongo():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['traintrack']
    return db

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
    return render_template("index.html", message="Note: Some records may be hidden. Check the detailed page for more information.", detail_link="/detail")

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
    qn = request.values.get("keyword", None)
    ftflag = request.values.get("future", False)
    if str(ftflag).lower() in ["true", "1"]:
        fd = "20991231"
    else:
        fd = (datetime.datetime.utcnow() + 
              datetime.timedelta(hours=8)).strftime('%Y%m%d')
    
    if qn is None:
        return jsonify({
            "success": False,
            "data": []
        })

    db = connect_mongo()
    collection = db.records
    k = detectType(qn)
    query_count += 1

    query_filter = {"day": {"$lt": fd}}
    if k == "train":
        query_filter["$or"] = [{"trainCodeA": qn}, {"trainCodeB": qn}]
    elif k == "car":
        query_filter["$or"] = [
            {"carA": {"$regex": f"^{qn}"}},
            {"carB": {"$regex": f"^{qn}"}}
        ]
    else:
        return jsonify({
            "success": True,
            "data": []
        })

    res = list(collection.find(
        query_filter,
        sort=[("timestamp", -1)],
        limit=50
    ))

    if len(res) == 0:
        return jsonify({
            "success": True,
            "data": []
        })

    return jsonify({
        "success": True,
        "data": list(reversed(sorted([{
            "runDate": time.strftime('%Y-%m-%d %H:%M', time.localtime(x["timestamp"])),
            "trainNum": [x["trainCodeA"], x["trainCodeB"]] if x["trainCodeB"] != "" else [x["trainCodeA"]],
            "trainCode": [x["carA"], x["carB"]] if x["carB"] != "" else [x["carA"]]
        } for x in res], key=lambda a: time.mktime(time.strptime(a["runDate"], '%Y-%m-%d %H:%M')))))
    })

@app.route("/api/query_summary")
def query_summary():
    global query_count
    query_count += 1
    qn = request.values.get("keyword", None)
    if qn is None:
        return jsonify({
            "success": False,
            "data": []
        })

    db = connect_mongo()
    collection = db.records
    eight_days_ago = (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - datetime.timedelta(days=8)).strftime('%Y%m%d')

    query_filter = {"day": {"$gte": eight_days_ago}}
    k = detectType(qn)
    if k == "train":
        query_filter["$or"] = [{"trainCodeA": qn}, {"trainCodeB": qn}]
    elif k == "car":
        query_filter["$or"] = [
            {"carA": {"$regex": f"^{qn}"}},
            {"carB": {"$regex": f"^{qn}"}}
        ]
    else:
        return jsonify({
            "success": True,
            "data": []
        })

    records = list(collection.find(query_filter, sort=[("timestamp", 1)]))

    summary = {}
    for record in records:
        day = record["day"]
        if day not in summary:
            summary[day] = {
                "earliest": record,
                "count": 0
            }
        summary[day]["count"] += 1

    data = []
    for day, info in sorted(summary.items(), key=lambda x: x[0], reverse=True):
        earliest = info["earliest"]
        data.append({
            "day": day,
            "earliest": {
                "runDate": time.strftime('%Y-%m-%d %H:%M', time.localtime(earliest["timestamp"])),
                "trainNum": [earliest["trainCodeA"], earliest["trainCodeB"]] if earliest["trainCodeB"] != "" else [earliest["trainCodeA"]],
                "trainCode": [earliest["carA"], earliest["carB"]] if earliest["carB"] != "" else [earliest["carA"]]
            },
            "hiddenCount": info["count"] - 1
        })

    return jsonify({
        "success": True,
        "data": data
    })

@app.route("/detail/<keyword>")
def detail_page(keyword):
    return render_template("detail.html", keyword=keyword)

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

@app.route("/sitemaps/<path:filename>")
def serve_sitemap_file(filename):
    return send_from_directory(SITEMAP_FOLDER, filename, mimetype="application/xml")

@app.route("/sitemap.xml")
def serve_sitemap_index():
    return send_from_directory(SITEMAP_FOLDER, SITEMAP_FILE, mimetype="application/xml")

@app.route("/update_sitemap")
def update_sitemap():
    key = request.args.get("key")
    if key != SITEMAP_KEY:
        return jsonify({"success": False, "message": "Invalid key"}), 403

    def generate_sitemap():
        db = connect_mongo()
        collection = db.records

        if not os.path.exists(SITEMAP_FOLDER):
            os.makedirs(SITEMAP_FOLDER)

        lastmod = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%dT00:00:00+08:00')

        static_sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd http://www.google.com/schemas/sitemap-image/1.1 http://www.google.com/schemas/sitemap-image/1.1/sitemap-image.xsd">
    <url>
        <loc>{BASE_URL}/</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{BASE_URL}/faq</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.2</priority>
    </url>
</urlset>"""

        static_sitemap_file = f"{SITEMAP_FOLDER}/static_sitemap.xml"
        with open(static_sitemap_file, "w", encoding="utf-8") as f:
            f.write(static_sitemap_content)

        keywords = set()
        for record in collection.find({}, {"carA": 1, "carB": 1, "trainCodeA": 1, "trainCodeB": 1}):
            keywords.update(filter(None, [record.get("carA"), record.get("carB"), record.get("trainCodeA"), record.get("trainCodeB")]))

        keywords = sorted(keywords)
        chunks = [keywords[i:i + 1000] for i in range(0, len(keywords), 1000)]

        sitemap_files = []
        for i, chunk in enumerate(chunks):
            sitemap_filename = f"{SITEMAP_FOLDER}/sitemap_part_{i + 1}.xml"
            sitemap_files.append(sitemap_filename)

            urls = [
                f"<url><loc>{BASE_URL}/detail/{keyword}</loc><lastmod>{lastmod}</lastmod><changefreq>always</changefreq><priority>0.4</priority></url>"
                for keyword in chunk
            ]

            sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd http://www.google.com/schemas/sitemap-image/1.1 http://www.google.com/schemas/sitemap-image/1.1/sitemap-image.xsd">
{''.join(urls)}
</urlset>"""

            with open(sitemap_filename, "w", encoding="utf-8") as f:
                f.write(sitemap_content)

        index_urls = [
            f"<sitemap><loc>{BASE_URL}/sitemaps/{os.path.basename(sitemap_file)}</loc><lastmod>{lastmod}</lastmod></sitemap>"
            for sitemap_file in sitemap_files
        ]
        index_urls.insert(0, f"<sitemap><loc>{BASE_URL}/sitemaps/static_sitemap.xml</loc><lastmod>{lastmod}</lastmod></sitemap>")

        index_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd http://www.google.com/schemas/sitemap-image/1.1 http://www.google.com/schemas/sitemap-image/1.1/sitemap-image.xsd">
{''.join(index_urls)}
</sitemapindex>"""

        with open(f"{SITEMAP_FOLDER}/{SITEMAP_FILE}", "w", encoding="utf-8") as f:
            f.write(index_content)

    threading.Thread(target=generate_sitemap).start()
    return jsonify({"success": True, "message": "Sitemap update started."})

if __name__ == "__main__":
    app.run("0.0.0.0", 8099, debug=True)
