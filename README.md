![LinuxReport logo](http://keithcu.com/LinuxReport2.png)
**and**
![CovidReport logo](http://keithcu.com//CovidReport.png)
--------------------------------------------------------------------------------
Simple, customizable and fast Linux and Covid-19 news site based on Python / Flask. Mean to be an automated http://drudgereport.com/ for news, updated hourly 24/7 and automatically! Typically returns pages in 2 ms.
Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.


```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```
