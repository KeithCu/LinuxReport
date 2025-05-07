#!/bin/bash
source /srv/http/LinuxReport2/venv/bin/activate
source /etc/update_headlines.conf
for dir in /srv/http/LinuxReport2 /srv/http/CovidReport2 /srv/http/trumpreport /srv/http/aireport /srv/http/pvreport; do
    cd "$dir" && python auto_update.py
done
deactivate
