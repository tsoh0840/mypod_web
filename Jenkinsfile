node {

    if ("${BRANCH_NAME}" == "main") {
        dockerUrl = "AA.dkr.ecr.ap-northeast-2.amazonaws.com/eks-AA"
        awsCredential = "AWS-AA"
        HELM_VAL = 'eks-AA/values-prod.yaml'
    } else if ("${BRANCH_NAME}" == "qa") {
        dockerUrl = "AA.dkr.ecr.ap-northeast-2.amazonaws.com/eks-AA"
        awsCredential = "AWS-AA"
        HELM_VAL = 'eks-AA/values-qa.yaml'
    } else {
        dockerUrl = "AA.dkr.ecr.ap-northeast-2.amazonaws.com/eks-AA"
        awsCredential = "AWS-AA"
        HELM_VAL = 'eks-AA/values-dev.yaml'
    }


    stage('Checkout') {
        checkout scm
    }

    stage('Build Docker Image') {
        app = docker.build("${dockerUrl}")
        docker.withRegistry("https://${dockerUrl}", "ecr:ap-northeast-2:${awsCredential}") {
                     app.push("${env.BUILD_NUMBER}")
                     app.push("latest")
        }
    }

    stage('Helm') {        
        def tempDir = "/var/lib/jenkins/workspace/eks-AA" + "_"+ "$BRANCH_NAME" + "_helm_charts"

        dir("$tempDir") {
            git branch: 'main', credentialsId: 'gitlab.AA', url: 'https://gitlab.AA/charts.git'

            sh "sed -i -e '1,// s/\\(tag: \\).*/\\1\"${env.BUILD_NUMBER}\"/' ${HELM_VAL}"
            withCredentials([usernamePassword(credentialsId: 'gitlab.AA', passwordVariable: 'GIT_PASSWORD', usernameVariable: 'GIT_USERNAME')]) {
                sh 'git config user.name AA'
                sh 'git config user.email AA@AA.com'
                sh 'git config credential.helper store'
                sh 'git commit -am "change tag version"'
                sh "git push origin HEAD:main --tags"
            }
        }

        sh "rm -rf $tempDir"
    }
}

