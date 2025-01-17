import subprocess
import pytz
import logging
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from datetime import timedelta


app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=3)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

# 잠금 해제 기간 (1시간)
lockout_period = timedelta(hours=1)
# 세션 만료 시간 (예: 30분)
session_timeout = timedelta(minutes=5)

# 타임존 설정
tz = pytz.timezone('UTC')

# 로그인 실패 횟수 기록
login_attempts = {}

logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

logging.info('Application started')

@app.before_request    #전처리 작업 수행
def before_request():
    session.permanent = True
    session.modified = True

@app.after_request     #후처리 작업 수행
def after_request(response):
    if not session:
        response = make_response(response)
        response.set_cookie('session', '', expires=0)
    return response

@app.before_request
def check_login():
    if request.endpoint in ['login', 'static']:
        return

    if 'logged_in' in session:    #유저 세션 시간 관리를 위함
        if session.get('last_activity'):
            last_activity = session['last_activity'].replace(tzinfo=tz)
            now = datetime.now(tz)
            if now - last_activity > session_timeout:
                session.pop('logged_in', None)
                session.pop('last_activity', None)
                return redirect(url_for('login'))
        session['last_activity'] = datetime.now(tz)
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])  # /login 페이지
def login():
    if request.method == 'POST':
        username = request.form['username']
        session['username'] = username  # 유저 이름을 세션에 저장
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.password == password:
            session['logged_in'] = True
            session['last_activity'] = datetime.now(tz)
            return redirect(url_for('list_eks_namespaces'))
        else:
            if username in login_attempts:
                login_attempts[username] += 1
            else:
                login_attempts[username] = 1

            if login_attempts.get(username, 0) >= 5:   # 로그인 5회 이상 실패 시 계정 1시간 잠금
                session['locked_until'] = datetime.now(tz) + lockout_period
                login_attempts.pop(username, None)  # 계정 잠금 시 실패 기록 제거
                return 'Your account is locked. Please try again later.'

            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')   #template 폴더의 login.html

@app.route('/logout')  #/logout 페이지
def logout():
    session.pop('logged_in', None)
    session.pop('last_activity', None)
    session.pop('username', None)  # 로그아웃 시 유저 이름 제거
    response = make_response(redirect(url_for('login')))  #logout 시 loing 페이지로 연결
    response.set_cookie('session', '', expires=0)  # 쿠키 삭제
    return response

def evict_pod(namespace, pod_name):
    try:
        config.load_incluster_config()  #k8s cluster config는 incluster load
        api = client.CoreV1Api()  #k8s 관련 클래스
        body = client.V1DeleteOptions()  # k8s 관련 클래스
        api.delete_namespaced_pod(name=pod_name, namespace=namespace, body=body)
        return True
    except ApiException as e: # except 처리 (e)
        print("Exception when calling CoreV1Api->delete_namespaced_pod: %s\n" % e) # except 된 {e} print
        return False

def get_pod_memory_usage(namespace, pod_name):
    try:
        config.load_incluster_config()
        api_instance = client.CustomObjectsApi()
        group = 'metrics.k8s.io'   #k8s cluster의 메트릭 서버로 api 발송
        version = 'v1beta1'
        plural = 'pods' #복수형
        
        api_response = api_instance.get_namespaced_custom_object(group, version, namespace, plural, pod_name)
        memory_usage = api_response['containers'][0]['usage']['memory']  
      
        core_api_instance = client.CoreV1Api()
        pod_response = core_api_instance.read_namespaced_pod(name=pod_name, namespace=namespace)
        memory_limit = pod_response.spec.containers[0].resources.limits['memory']
        
        def parse_memory_string(memory_str):  # ram usage 표기 변환
            if memory_str.endswith('Mi'):
                return int(memory_str[:-2]) / 1024
            elif memory_str.endswith('Gi'):
                return int(memory_str[:-2])
            elif memory_str.endswith('Ki'):
                return int(memory_str[:-2]) / (1024 * 1024)
            elif memory_str.endswith('Ti'):
                return int(memory_str[:-2]) * 1024
            else:
                return int(memory_str) / (1024 * 1024 * 1024)  # Assume it's in bytes if no unit

        current_memory_usage_gi = parse_memory_string(memory_usage)
        memory_limit_gi = parse_memory_string(memory_limit)
        
        memory_usage_percentage = (current_memory_usage_gi / memory_limit_gi) * 100
        
        return f"{current_memory_usage_gi:.2f}Gi ({memory_usage_percentage:.2f}%)"
    except ApiException as e:
        print("Exception when calling CustomObjectsApi->get_namespaced_custom_object: %s\n" % e)
        return None

@app.route('/')
def list_eks_namespaces():
    excluded_namespaces = {'argocd', 'default', 'eks-ram-alert', 'external-secrets', 
                           'fluentbit', 'karpenter', 'keda', 'kube-system', 
                           'kubecost', 'prometheus', 'velero'}

    config.load_incluster_config()
    v1 = client.CoreV1Api()
    namespaces = v1.list_namespace().items
    namespace_names = []

    for ns in namespaces:
        namespace = ns.metadata.name
        if namespace not in excluded_namespaces:
            pods = v1.list_namespaced_pod(namespace).items
            if pods:
                namespace_names.append(namespace)

    template = '''
    <!doctype html>
    <html>
    <head>
        <title>Namespace List</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f4f4f4;
                margin: 0;
                padding: 0;
            }
            .container {
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background-color: #fff;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                border-radius: 8px;
            }
            h1 {
                text-align: center;
                color: #333;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }
            th {
                background-color: #f8f8f8;
            }
            button {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                text-align: center;
                text-decoration: none;
                display: inline-block;
                font-size: 14px;
                margin: 4px 2px;
                cursor: pointer;
                border-radius: 4px;
            }
            button:hover {
                background-color: #0056b3;
            }
            .pod-list {
                display: none;
                margin-top: 10px;
            }
            .pod-item {
                display: flex;
                align-items: center;
                margin-bottom: 5px;
            }
            .pod-item span {
                margin-left: 10px;
            }
            .evict-button {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 5px 10px;
                margin-left: 10px;
                cursor: pointer;
                border-radius: 4px;
            }
            .evict-button:hover {
                background-color: #c82333;
            }
        </style>
        <script>
            function loadPods(namespace) {
                const podsList = document.getElementById('pods-' + namespace);
                if (podsList.style.display === 'none' || podsList.innerHTML === '') {
                    fetch('/namespaces/' + namespace)
                            .then(response => response.json())
                            .then(data => {
                                podsList.innerHTML = data.map(pod => `
                                    <div class="pod-item">
                                        ${pod}
                                        <span id="usage-${pod}"></span>
                                        <button class="evict-button" onclick="confirmEvict('${namespace}', '${pod}')">Evict</button>
                                    </div>`).join('');
                                loadMemoryUsage(namespace, data);
                                podsList.style.display = 'block';
                            });
                } else {
                    podsList.style.display = 'none';
                }
            }

            function loadMemoryUsage(namespace, pods) {
                pods.forEach(pod => {
                    fetch('/memory-usage/' + namespace + '/' + pod, { method: 'GET' })
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('usage-' + pod).innerText = ' - Memory Usage: ' + data.usage;
                    });
                });
            }

            function confirmEvict(namespace, podName) {
                if (confirm('정말 evict 하시겠습니까?')) {
                    evictPod(namespace, podName);
                } else {
                    return false;
                }
            }

            function evictPod(namespace, podName) {
                fetch('/evict/' + namespace + '/' + podName, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(podName + '이 정상적으로 evict 되었습니다.');
                    } else {
                        alert(podName + ' evict 실패. 수동 작업 요망.');
                    }
                });
            }
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Namespaces</h1>
            <table>
                <tr>
                    <th>Namespace</th>
                    <th>Action</th>
                </tr>
                {% for name in namespace_names %}
                    <tr>
                        <td>{{ name }}</td>
                        <td>
                            <button onclick="loadPods('{{ name }}')">Show Pods</button>
                            <div id="pods-{{ name }}" class="pod-list"></div>
                        </td>
                    </tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    '''

    return render_template_string(template, namespace_names=namespace_names)

@app.route('/namespaces/<namespace>')  
def list_pods_in_namespace(namespace):
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace).items
    pod_names = [pod.metadata.name for pod in pods]
    return jsonify(pod_names) # json형태로 변환

@app.route('/evict/<namespace>/<pod_name>', methods=['POST'])
def evict_pod_endpoint(namespace, pod_name):
    success = evict_pod(namespace, pod_name)
    
    username = session.get('username')  # 현재 로그인한 유저 정보 가져오기
    if success:
        logging.info(f"User '{username}' evicted pod {pod_name} in namespace {namespace} successfully.")  #evict 수행 시, user name logging
    else:
        logging.error(f"User '{username}' failed to evict pod {pod_name} in namespace {namespace}.")
    
    return jsonify({'success': success})

@app.route('/memory-usage/<namespace>/<pod_name>', methods=['GET'])
def get_memory_usage(namespace, pod_name):
    memory_usage = get_pod_memory_usage(namespace, pod_name)
    return jsonify({'usage': memory_usage})
                           
if __name__ == '__main__':
    #app.run(debug=True)
    with app.app_context():        # db 설정 부분
        migrate.init_app(app, db)        

        db.create_all()
        
        users = [  # 유저 추가
            {'username': 'AA', 'password': 'AA'},
            {'username': 'BB', 'password': 'BB!'},
            {'username': 'CC', 'password': 'CC'}
        ]
        for user_data in users: 
            user = User.query.filter_by(username=user_data['username']).first()
            if user:                
                user.password = user_data['password']
            else:                
                user = User(**user_data)
                db.session.add(user)
        
        db.session.commit()

    app.run(host='0.0.0.0', port=80) # 0.0.0.0:80 오픈. 하지만 elb(target port=80) sg에 의해 office only로 적용된다.
