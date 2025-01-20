![LinuxReport logo](https://keithcu.com/LinuxReport2.png)
**and**
![CovidReport logo](https://keithcu.com//CovidReport.png)
**and**
![AIReport_logo](https://github.com/KeithCu/LinuxReport/blob/master/static/images/AIReport.png)
--------------------------------------------------------------------------------
Simple and fast news site based on Python / Flask. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7, and customizable by the user, including custom feeds and the critically important dark mode.

Here's the running code: https://linuxreport.net 

Takes advantage of thread pools and process pools to be high-performance and scalable. Some people incorrectly say that Python is slow, but this app typically starts returning the page after less than 10 lines of my Python code.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```
