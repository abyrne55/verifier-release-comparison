FROM registry.access.redhat.com/ubi9/python-39:latest

COPY . /opt/app-root/src

RUN pip install -r requirements.txt

CMD python3 analyze_csv.py 
