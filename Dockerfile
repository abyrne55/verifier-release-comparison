FROM registry.access.redhat.com/ubi9/python-39:latest

COPY requirements.txt /opt/app-root/src

RUN pip install -r requirements.txt

COPY . /opt/app-root/src

CMD python3 analyze_csv.py 
