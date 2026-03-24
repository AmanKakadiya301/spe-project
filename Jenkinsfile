pipeline {
    agent any

    environment {
        DOCKER_IMAGE           = 'amankakadiya301/fintech-stock-app'
        DOCKER_TAG             = "build-${BUILD_NUMBER}"
        REGISTRY_CREDENTIALS   = 'dockerhub-credentials'
        KUBECONFIG_CREDENTIALS = 'k8s-kubeconfig'
        ALERT_EMAIL            = 'kakadiyaaman2004@gmail.com'
        // Minimum test coverage % required to pass the build
        COVERAGE_THRESHOLD     = '60'
    }

    triggers {
        githubPush()
    }

    stages {

        stage('Checkout') {
            steps {
                echo 'Checking out source code...'
                checkout scm
            }
        }

        // NEW: Lint Python files before running tests
        // Catches syntax errors and obvious bugs immediately
        stage('Lint') {
            steps {
                echo 'Linting Python source files...'
                sh '''
                    python3 -m venv venv || true
                    . venv/bin/activate || true
                    pip install flake8 --quiet
                    # E501 = line too long (relaxed for this project)
                    # W503 = line break before binary operator (style choice)
                    flake8 app/ --max-line-length=120 --ignore=E501,W503 \
                        --exclude=app/tests/,app/instance/ || true
                '''
            }
        }

        stage('Lint & Secrets Check') {
            steps {
                echo 'Running Trivy filesystem scan for baked-in secrets...'
                sh './trivy-scan.sh fs .'
            }
        }

        // IMPROVED: Added --cov flag and coverage gate
        stage('Unit Tests') {
            steps {
                echo 'Running Python unit tests with coverage...'
                sh '''
                    python3 -m venv venv || true
                    . venv/bin/activate || true
                    pip install -r app/requirements.txt --quiet
                    python -m pytest app/tests/ -v \
                        --junitxml=test-results.xml \
                        --cov=app \
                        --cov-report=xml:coverage.xml \
                        --cov-report=html:htmlcov \
                        --cov-report=term-missing \
                        --cov-fail-under=${COVERAGE_THRESHOLD}
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                    // Publish HTML coverage report in Jenkins
                    publishHTML(target: [
                        allowMissing:          false,
                        alwaysLinkToLastBuild: true,
                        keepAll:               true,
                        reportDir:             'htmlcov',
                        reportFiles:           'index.html',
                        reportName:            'Coverage Report'
                    ])
                }
            }
        }

        // IMPROVED: Uses --cache-from to speed up repeated builds via layer caching
        stage('Build Docker Image') {
            steps {
                echo "Building image: ${DOCKER_IMAGE}:${DOCKER_TAG}"
                sh """
                    docker pull ${DOCKER_IMAGE}:latest || true
                    docker build \
                        --cache-from ${DOCKER_IMAGE}:latest \
                        -t ${DOCKER_IMAGE}:${DOCKER_TAG} \
                        -t ${DOCKER_IMAGE}:latest .
                """
            }
        }

        stage('Container Security Scan') {
            steps {
                echo 'Scanning Docker image for HIGH/CRITICAL CVEs...'
                sh "./trivy-scan.sh image ${DOCKER_IMAGE}:${DOCKER_TAG}"
            }
        }

        stage('Push to Registry') {
            steps {
                echo 'Pushing image to DockerHub...'
                withCredentials([usernamePassword(
                    credentialsId: env.REGISTRY_CREDENTIALS,
                    passwordVariable: 'DOCKER_PASS',
                    usernameVariable: 'DOCKER_USER'
                )]) {
                    sh """
                        echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin
                        docker push ${DOCKER_IMAGE}:${DOCKER_TAG}
                        docker push ${DOCKER_IMAGE}:latest
                    """
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                echo 'Deploying to Kubernetes cluster...'
                sh """
                    export KUBECONFIG=/var/lib/jenkins/jenkins-kubeconfig.yaml

                    sed -i "s|image: amankakadiya301/fintech-stock-app:latest|image: ${DOCKER_IMAGE}:${DOCKER_TAG}|g" k8s/deployment.yaml

                    kubectl apply -f k8s/namespace.yaml
                    kubectl apply -f k8s/deployment.yaml
                    kubectl apply -f k8s/service.yaml
                    kubectl apply -f k8s/hpa.yaml

                    kubectl rollout status deployment/stock-app-deployment \
                        -n fintech-prod --timeout=120s
                """
            }
        }

        // NEW: Smoke test — hit /health after deploy to confirm pod is alive
        stage('Post-Deploy Smoke Test') {
            steps {
                echo 'Running post-deployment smoke test...'
                sh """
                    export KUBECONFIG=/var/lib/jenkins/jenkins-kubeconfig.yaml
                    # Wait for service to be reachable
                    sleep 10
                    # Port-forward briefly and hit /health
                    kubectl port-forward svc/stock-app-service 18080:5000 \
                        -n fintech-prod &
                    PF_PID=\$!
                    sleep 5
                    curl -sf http://localhost:18080/health | grep '"status":"ok"'
                    kill \$PF_PID || true
                    echo 'Smoke test PASSED'
                """
            }
        }
    }

    post {
        success {
            echo '✅ Pipeline completed successfully!'
            mail to:      "${env.ALERT_EMAIL}",
                 subject: "SUCCESS: ${currentBuild.fullDisplayName}",
                 body:    "Pipeline passed.\n\nProject: ${env.JOB_NAME}\nBuild: ${env.BUILD_NUMBER}\nLogs: ${env.BUILD_URL}"
        }
        failure {
            echo '❌ Pipeline failed!'
            mail to:      "${env.ALERT_EMAIL}",
                 subject: "FAILED: ${currentBuild.fullDisplayName}",
                 body:    "Pipeline failed.\n\nProject: ${env.JOB_NAME}\nBuild: ${env.BUILD_NUMBER}\nLogs: ${env.BUILD_URL}"
        }
        always {
            echo 'Cleaning workspace...'
            sh 'docker rmi ${DOCKER_IMAGE}:${DOCKER_TAG} || true'
            cleanWs()
        }
    }
}
