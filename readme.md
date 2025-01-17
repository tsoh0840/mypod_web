# mypod.kr Repository

---
## 생성 목적
- ram-alert 발생 시, 빠른 대응을 위해 노트북을 휴대하거나, 다른 팀원분들께 연락, 급한 상황시 빠르게 귀가해야 하는 불상사 발생.
- 이를 해결하고자, 스마트폰으로 접근, 버튼 클릭으로 작업 처리할 수 있도록 구성.


## About Service 
1. 해당 서비스는 ram-alert을 발생시키지 않습니다.
2. ram-alert이 grafana에서 발생하는 경우, 원격에서 pod 수동 evict이 가능하게끔 하는 서비스입니다.
3. flask로 웹을 생성, sqlite로 db를 관리하고 있습니다. 소스는 python으로 작성되었습니다.
4. 해당 서비스는 사내 vpn 접속 시 접근이 가능합니다.
5. 로그인 5회 실패 시 계정이 1시간동안 잠깁니다.
6. 모든 evict 행위는 pod에 기록됩니다.


## Logic
1. mypod.kr 접속 
2. eks-ram-alert pod에서 PROD-AA cluster로 api 전송. namespace list get
3. mypod.AA.kr에 namespace list 출력
4. pod 버튼 클릭
5. service pod에서 cluster로 api 전송. pod list 및 metrics get
6. mypod.kr에 pod list 및 Usage ram % 출력
6. evict 버튼 클릭
7. service pod에서 cluster로 api 전송. pod delete 명령 실행
8. mypod.kr에 메시지 출력
9. mypod.kr에 메시지 출력
10. evict 시 pod에 로그 저장



## 배포 순서
1. 소스 업데이트 (https://gitlab.AA)
2. git push
3. Jenkins build
4. argocd sync
5. 결과 확인


## EKS cluster Auth
- EKS cluster api call Auth는 Cluster Role, Cluster Role Binding을 통해 취득한다.

## User PW 변경
- 내부 보관용 소스에서 수정 필요. (하단에 user, pw 라인 있음) 
- url : https://gitlab.AA
- pw 변경 후 pod 재시작하면 적용 된다. 

