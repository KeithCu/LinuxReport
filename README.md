![LinuxReport logo](http://keithcu.com/LinuxReport2.png)
**and**
![CovidReport logo](http://keithcu.com//CovidReport.png)
--------------------------------------------------------------------------------
Simple, customizable and fast Linux and Covid-19 news site based on Python / Flask. Takes advantage of thread pools and process pools of Apache to be high-performance and scalable. Some people People incorrectly say that Python is slow, but this typically starts returning the page in 2 ms. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```
