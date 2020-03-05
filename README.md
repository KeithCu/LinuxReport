![LinuxReport logo](http://linuxreport.net/static/images/LinuxReport2.png)
**and**
![CovidReport logo](http://covidreport.net/static/images/CovidReport.png)
--------------------------------------------------------------------------------
Linux and Covid-19 news site based on Python / Flask. Feel free to request more default RSS feeds, or send pull requests.

To run on your own machine, You need to setup Python and a web server.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```
Web servers need a configuration file to tell it where the flask software is. A sample Apache one is included.
