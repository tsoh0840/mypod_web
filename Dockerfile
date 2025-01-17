FROM python:3.7-slim
WORKDIR /usr/src/app
RUN pip install pytz flask SQLAlchemy kubernetes urllib3==1.26.7 flask_sqlalchemy flask_migrate
COPY . /usr/src/app
EXPOSE 80
CMD ["python", "/usr/src/app/app.py"]