pipeline {
    agent any
    environment {
        DOCKER_IMAGE         = 'amankakadiya301/fintech-stock-app'
        DOCKER_TAG           = "build-${BUILD_NUMBER}"
        REGISTRY_CREDENTIALS = 'dockerhub-credentials'
        ALERT_EMAIL          = 'kakadiyaaman2004@gmail.com'
        DEPLOY_NAMESPACE     = 'fintech-prod'
    }
    triggers { githubPush() }
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
    }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_COMMIT_MSG = sh(script: 'git log -1 --pretty=%B', returnStdout: true).trim()
                    env.GIT_AUTHOR    = sh(script: 'git log -1 --pretty=%an', returnStdout: true).trim()
                }
            }
        }
        stage('Lint') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install black pylint isort --quiet
                    black --check app/ || true
                    isort --check-only app/ || true
                    pylint app/*.py --disable=C0114,C0115,C0116,R0903,W0212 --fail-under=7.0 || true
                '''
            }
        }
        stage('Trivy FS Scan') {
            steps { sh './trivy-scan.sh fs .' }
        }
        stage('OWASP Dep Check') {
            steps {
                sh '''
                    . venv/bin/activate || true
                    pip install pip-audit --quiet
                    pip-audit -r requirements.txt --format=json --output=pip-audit.json || true
                    pip-audit -r requirements.txt
                '''
            }
            post { always { archiveArtifacts artifacts: 'pip-audit.json', allowEmptyArchive: true } }
        }
        stage('Unit Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    pip install -r requirements.txt pytest pytest-cov --quiet
                    pytest app/tests/ -v --cov=app --cov-report=xml:coverage.xml --junitxml=test-results.xml
                '''
            }
            post { always { junit 'test-results.xml' } }
        }
        stage('Build Docker Image') {
            steps {
                sh """
                    DOCKER_BUILDKIT=1 docker build \
                        --cache-from ${DOCKER_IMAGE}:latest \
                        --build-arg BUILDKIT_INLINE_CACHE=1 \
                        -t ${DOCKER_IMAGE}:${DOCKER_TAG} \
                        -t ${DOCKER_IMAGE}:latest .
                """
            }
        }
        stage('Trivy Image Scan') {
            steps { sh "./trivy-scan.sh image ${DOCKER_IMAGE}:${DOCKER_TAG}" }
        }
        stage('Push to DockerHub') {
            steps {
                withCredentials([usernamePassword(credentialsId: env.REGISTRY_CREDENTIALS,
                    usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    sh """
                        echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin
                        docker push ${DOCKER_IMAGE}:${DOCKER_TAG}
                        docker push ${DOCKER_IMAGE}:latest
                    """
                }
            }
        }
        stage('Deploy to Staging') {
            when { branch 'develop' }
            steps {
                sh """
                    export KUBECONFIG=/var/lib/jenkins/jenkins-kubeconfig.yaml
                    sed -i "s|image: amankakadiya301/fintech-stock-app:latest|image: ${DOCKER_IMAGE}:${DOCKER_TAG}|g" k8s/deployment.yaml
                    kubectl apply -f k8s/namespace.yaml
                    kubectl apply -f k8s/deployment.yaml
                    kubectl apply -f k8s/service.yaml
                    kubectl rollout status deployment/stock-app-deployment -n fintech-staging --timeout=90s
                """
            }
        }
        stage('Deploy to Production') {
            when { branch 'main' }
            steps {
                sh """
                    export KUBECONFIG=/var/lib/jenkins/jenkins-kubeconfig.yaml
                    sed -i "s|image: amankakadiya301/fintech-stock-app:latest|image: ${DOCKER_IMAGE}:${DOCKER_TAG}|g" k8s/deployment.yaml
                    kubectl apply -f k8s/namespace.yaml
                    kubectl apply -f k8s/deployment.yaml
                    kubectl apply -f k8s/service.yaml
                    kubectl apply -f k8s/hpa.yaml
                    kubectl rollout status deployment/stock-app-deployment -n ${DEPLOY_NAMESPACE} --timeout=90s
                """
            }
        }
        stage('Health Check') {
            steps {
                sh """
                    export KUBECONFIG=/var/lib/jenkins/jenkins-kubeconfig.yaml
                    sleep 10
                    POD=\$(kubectl get pod -n ${DEPLOY_NAMESPACE} -l app=stock-app -o jsonpath='{.items[0].metadata.name}')
                    kubectl exec -n ${DEPLOY_NAMESPACE} \$POD -- python -c \
                        "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"
                """
            }
        }
    }
    post {
        success {
            mail to: "${env.ALERT_EMAIL}",
                subject: "SUCCESS: ${currentBuild.fullDisplayName}",
                body: "Pipeline passed.\n\nBuild: #${env.BUILD_NUMBER}\nImage: ${env.DOCKER_IMAGE}:${env.DOCKER_TAG}\nLogs: ${env.BUILD_URL}"
        }
        failure {
            sh """
                export KUBECONFIG=/var/lib/jenkins/jenkins-kubeconfig.yaml
                kubectl rollout undo deployment/stock-app-deployment -n ${DEPLOY_NAMESPACE} || true
            """
            mail to: "${env.ALERT_EMAIL}",
                subject: "FAILED: ${currentBuild.fullDisplayName}",
                body: "Pipeline FAILED. Auto-rollback attempted.\n\nBuild: #${env.BUILD_NUMBER}\nLogs: ${env.BUILD_URL}"
        }
        always {
            sh 'docker rmi ${DOCKER_IMAGE}:${DOCKER_TAG} 2>/dev/null || true'
            cleanWs()
        }
    }
}
