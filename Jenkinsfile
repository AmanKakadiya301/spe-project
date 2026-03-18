pipeline {
    agent any
    
    // Environment Variables specific to the pipeline run
    environment {
        DOCKER_IMAGE = 'amankakadiya301/fintech-stock-app'
        DOCKER_TAG   = "build-${BUILD_NUMBER}"
        REGISTRY_CREDENTIALS = 'dockerhub-credentials'
        KUBECONFIG_CREDENTIALS = 'k8s-kubeconfig'
        ALERT_EMAIL  = 'kakadiyaaman2004@gmail.com' // Email to receive success/failure alerts
    }

    // Trigger on code push to main branch
    triggers {
        githubPush()
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Checking out code from Git...'
                checkout scm
            }
        }

        stage('Lint & Secrets Check') {
            steps {
                echo 'Running Trivy filesystem scan to check for baked-in secrets...'
                sh './trivy-scan.sh fs .'
            }
        }

        stage('Unit Tests') {
            steps {
                echo 'Running Python unit tests...'
                sh '''
                    # In a real environment, you might use a python agent or virtualenv
                    python3 -m venv venv || true
                    . venv/bin/activate || true
                    pip install -r app/requirements.txt
                    python -m pytest app/tests/ -v --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Building image: ${DOCKER_IMAGE}:${DOCKER_TAG}"
                sh "docker build -t ${DOCKER_IMAGE}:${DOCKER_TAG} -t ${DOCKER_IMAGE}:latest ."
            }
        }

        stage('Container Security Scan') {
            steps {
                echo 'Scanning built image for vulnerabilities...'
                sh "./trivy-scan.sh image ${DOCKER_IMAGE}:${DOCKER_TAG}"
            }
        }

        stage('Push to Registry') {
            steps {
                echo 'Pushing image to DockerHub...'
                withCredentials([usernamePassword(credentialsId: env.REGISTRY_CREDENTIALS, passwordVariable: 'DOCKER_PASS', usernameVariable: 'DOCKER_USER')]) {
                    sh "echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin"
                    sh "docker push ${DOCKER_IMAGE}:${DOCKER_TAG}"
                    sh "docker push ${DOCKER_IMAGE}:latest"
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                echo 'Deploying to Kubernetes cluster...'
                sh '''
                    # Bypass Jenkins Secrets to use the natively generated embedded Kubeconfig
                    export KUBECONFIG=/home/amank/jenkins-kubeconfig.yaml
                    
                    # Replace the image tag in the deployment file
                    sed -i "s|image: amand2011/fintech-stock-app:latest|image: ${DOCKER_IMAGE}:${DOCKER_TAG}|g" k8s/deployment.yaml
                    
                    # Apply Kubernetes manifests
                    kubectl apply -f k8s/namespace.yaml
                    kubectl apply -f k8s/deployment.yaml
                    kubectl apply -f k8s/service.yaml
                    kubectl apply -f k8s/hpa.yaml
                    
                    # Verify rollout status
                    kubectl rollout status deployment/stock-app-deployment -n fintech-prod --timeout=90s
                '''
            }
        }
    }

    post {
        success {
            echo '✅ Pipeline completed successfully!'
            mail to: "${env.ALERT_EMAIL}",
                 subject: "SUCCESS: Pipeline ${currentBuild.fullDisplayName}",
                 body: "Good news! The Jenkins pipeline completed successfully.\n\nProject: ${env.JOB_NAME}\nBuild: ${env.BUILD_NUMBER}\nLogs: ${env.BUILD_URL}"
        }
        failure {
            echo '❌ Pipeline failed! Please check the logs.'
            mail to: "${env.ALERT_EMAIL}",
                 subject: "FAILED: Pipeline ${currentBuild.fullDisplayName}",
                 body: "Attention! The Jenkins pipeline failed.\n\nProject: ${env.JOB_NAME}\nBuild: ${env.BUILD_NUMBER}\nLogs: ${env.BUILD_URL}\nPlease check the console output."
        }
        always {
            echo 'Cleaning up workspace...'
            cleanWs() // Deletes the workspace content to save disk space
        }
    }
}
