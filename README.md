![LinuxReport logo](http://keithcu.com/LinuxReport2.png)
**and**
![CovidReport logo](http://keithcu.com//CovidReport.png)
--------------------------------------------------------------------------------
Simple and fast Linux and Covid-19 news site based on Python / Flask. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7, and customizable.

Takes advantage of thread pools and process pools to be high-performance and scalable. Some people incorrectly say that Python is slow, but this app typically starts returning the page in 2 ms.

DrudgeReport handles about 23 million page-views per day, which is 266 requests per second. Ignoring the images, which could be cheaply stored in a CDN, one [8-core, $160 per month Linode](https://www.linode.com/pricing/) would be able handle that amount of traffic.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```
