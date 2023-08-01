FROM registry.access.redhat.com/ubi9/python-39:latest

COPY . /opt/app-root/src

RUN pip install -r requirements.txt

ENV NETRC=/opt/app-root/src/.netrc

CMD python3 analyze_csv.py 
