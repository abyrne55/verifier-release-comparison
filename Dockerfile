FROM registry.access.redhat.com/ubi9/python-39:latest

COPY . /opt/app-root/src

CMD python3 analyze_csv.py 
