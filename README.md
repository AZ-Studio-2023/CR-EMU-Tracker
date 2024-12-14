# <center>CR-EMU-Tracker</center>
#### <center>中国铁路动车组担当运行追踪查询</center>
*<center>Part of RailGo Project</center>*

## 介绍
本软件类似于[emu-log](https://github.com/Arnie97/emu-log)项目，可以侦测并记录动车组的担当运行信息。

本软件还是 RailGo 的官方数据源。

## 特点
- **可查询未来车次的担当信息。**
- (理论) 无需维护车辆列表，自动适应。
- 采用多线程结构，爬取快速。
- 轻量简便，300行 (`parser.py`) 解决一切问题。

## 运行

`pip install -r requirements.txt`

启动爬虫：`python parser.py --day {需要获取的未来天}`

## 服务
https://crtracker.azteam.cn/

如非批量使用数据，可以直接请求我们的服务，详见网站API文档。

## 版权信息

开发人员：
- @TKP30
- @辰墨 （zlk-sys）
- @mstouk57g

采用GPL许可证，请按照许可证允许范围运用。**禁止用于商业软件。**

需要批量数据供研究等使用的请[联系作者](mailto:hahaguo1107@foxmail.com)。
